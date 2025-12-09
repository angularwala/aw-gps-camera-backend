from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from collections import defaultdict
from datetime import datetime, timedelta
import time
import hashlib

# Simple in-memory rate limiter (for production, use Redis)
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
        self.cleanup_interval = 60  # Clean up every 60 seconds
        self.last_cleanup = time.time()
    
    def is_allowed(self, key: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
        """
        Check if request is allowed based on rate limit
        Args:
            key: Unique identifier (IP address, user ID, etc.)
            max_requests: Maximum requests allowed in the time window
            window_seconds: Time window in seconds
        """
        current_time = time.time()
        
        # Periodic cleanup
        if current_time - self.last_cleanup > self.cleanup_interval:
            self.cleanup()
            self.last_cleanup = current_time
        
        # Filter requests within the time window
        cutoff_time = current_time - window_seconds
        self.requests[key] = [req_time for req_time in self.requests[key] if req_time > cutoff_time]
        
        # Check if limit is exceeded
        if len(self.requests[key]) >= max_requests:
            return False
        
        # Add current request
        self.requests[key].append(current_time)
        return True
    
    def cleanup(self):
        """Remove old entries"""
        current_time = time.time()
        cutoff_time = current_time - 300  # Keep last 5 minutes
        
        for key in list(self.requests.keys()):
            self.requests[key] = [req_time for req_time in self.requests[key] if req_time > cutoff_time]
            if not self.requests[key]:
                del self.requests[key]

# Global rate limiter instance
rate_limiter = RateLimiter()

class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive security middleware for:
    - Rate limiting
    - Security headers
    - XSS protection
    - Request size limits
    """
    
    async def dispatch(self, request: Request, call_next):
        # Get client IP (handle None case for proxied requests)
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip and request.client:
            client_ip = request.client.host
        if not client_ip:
            client_ip = "unknown"
        
        # Rate limiting (100 requests per minute per IP)
        if not rate_limiter.is_allowed(client_ip, max_requests=100, window_seconds=60):
            return Response(
                content="Rate limit exceeded. Please try again later.",
                status_code=429,
                headers={"Retry-After": "60"}
            )
        
        # Additional rate limiting for authentication endpoints (stricter)
        if "/api/auth/" in request.url.path:
            if not rate_limiter.is_allowed(f"{client_ip}:auth", max_requests=10, window_seconds=60):
                return Response(
                    content="Too many authentication attempts. Please try again later.",
                    status_code=429,
                    headers={"Retry-After": "60"}
                )
        
        # Request size limit (10MB)
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 10 * 1024 * 1024:
            return Response(
                content="Request body too large",
                status_code=413
            )
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Content Security Policy - Different policies for docs vs application
        if request.url.path in ["/docs", "/redoc"] or request.url.path.startswith("/openapi"):
            # Relaxed CSP for FastAPI documentation (Swagger UI/ReDoc)
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https://cdn.jsdelivr.net; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )
        else:
            # Strict CSP for application endpoints
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' https://nominatim.openstreetmap.org; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )
        
        # Strict Transport Security (HTTPS only)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


def sanitize_input(text: str) -> str:
    """
    Sanitize user input to prevent XSS attacks
    """
    if not text:
        return text
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Basic HTML entity encoding for dangerous characters
    dangerous_chars = {
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '&': '&amp;',
        '/': '&#x2F;'
    }
    
    for char, entity in dangerous_chars.items():
        text = text.replace(char, entity)
    
    return text


def validate_file_upload(filename: str, allowed_extensions: set = None) -> tuple[bool, str]:
    """
    Validate uploaded file for security
    Returns: (is_valid, error_message)
    """
    if allowed_extensions is None:
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.pdf', '.webp'}
    
    if not filename:
        return False, "Filename is required"
    
    # Check for path traversal attempts
    if '..' in filename or '/' in filename or '\\' in filename:
        return False, "Invalid filename - path traversal detected"
    
    # Check file extension
    file_ext = filename.lower().split('.')[-1] if '.' in filename else ''
    if f'.{file_ext}' not in allowed_extensions:
        return False, f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
    
    # Check filename length
    if len(filename) > 255:
        return False, "Filename too long"
    
    # Check for executable extensions (double check)
    dangerous_extensions = {'.exe', '.bat', '.sh', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js'}
    if f'.{file_ext}' in dangerous_extensions:
        return False, "Executable files are not allowed"
    
    return True, ""


def hash_password_salt(password: str) -> str:
    """
    Create a salted hash of password for additional security
    """
    import hashlib
    import os
    
    salt = os.urandom(32)
    pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + pwdhash.hex()


def verify_password_salt(stored_password: str, provided_password: str) -> bool:
    """
    Verify a password against a salted hash
    """
    import hashlib
    
    salt = bytes.fromhex(stored_password[:64])
    stored_hash = stored_password[64:]
    pwdhash = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)
    return pwdhash.hex() == stored_hash
