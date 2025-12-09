from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import JWTError, jwt
from config import settings
import hashlib
import os
import base64
import re
import secrets

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHash
    ARGON2_AVAILABLE = True
    ph = PasswordHasher(
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        salt_len=16
    )
except ImportError:
    ARGON2_AVAILABLE = False
    ph = None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash using Argon2 (primary) or PBKDF2 (fallback)"""
    if not plain_password or not hashed_password:
        return False
    
    # Try Argon2 first (new format starts with $argon2)
    if ARGON2_AVAILABLE and hashed_password.startswith('$argon2'):
        peppered_password = plain_password + settings.password_pepper
        try:
            ph.verify(hashed_password, peppered_password)
            return True
        except (VerifyMismatchError, InvalidHash):
            return False
        except Exception:
            return False
    
    # Fallback to PBKDF2 for legacy passwords (created without pepper)
    try:
        parts = hashed_password.split('$')
        if len(parts) != 2:
            return False
        
        salt = base64.b64decode(parts[0])
        stored_hash = base64.b64decode(parts[1])
        
        # Verify legacy password without pepper (backward compatible)
        new_hash = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt, 100000)
        return secrets.compare_digest(new_hash, stored_hash)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Hash a password using Argon2id (recommended) with pepper"""
    peppered_password = password + settings.password_pepper
    
    if ARGON2_AVAILABLE:
        return ph.hash(peppered_password)
    
    # Fallback to PBKDF2
    salt = os.urandom(32)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', peppered_password.encode('utf-8'), salt, 100000)
    return f"{base64.b64encode(salt).decode('utf-8')}${base64.b64encode(pwd_hash).decode('utf-8')}"

def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Validate password meets security requirements"""
    if len(password) < settings.min_password_length:
        return False, f"Password must be at least {settings.min_password_length} characters"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    return True, "Password is strong"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
        "jti": secrets.token_urlsafe(16)
    })
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """Create a long-lived refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16)
    })
    encoded_jwt = jwt.encode(to_encode, settings.refresh_secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def decode_token(token: str, token_type: str = "access") -> Optional[dict]:
    """Decode and validate a token"""
    try:
        secret = settings.secret_key if token_type == "access" else settings.refresh_secret_key
        payload = jwt.decode(token, secret, algorithms=[settings.algorithm])
        
        # Verify token type
        if payload.get("type") != token_type:
            return None
        
        return payload
    except JWTError:
        return None

def decode_access_token(token: str) -> Optional[dict]:
    """Decode access token"""
    return decode_token(token, "access")

def decode_refresh_token(token: str) -> Optional[dict]:
    """Decode refresh token"""
    return decode_token(token, "refresh")

def generate_otp(length: int = 6) -> str:
    """Generate a secure OTP"""
    return ''.join(secrets.choice('0123456789') for _ in range(length))

def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """Mask sensitive data for logging"""
    if not data or len(data) <= visible_chars:
        return '*' * len(data) if data else ''
    return data[:visible_chars] + '*' * (len(data) - visible_chars)
