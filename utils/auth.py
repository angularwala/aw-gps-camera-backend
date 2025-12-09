"""
Authentication utilities for WebSocket and token verification
"""
from typing import Optional
from utils.security import decode_access_token


def verify_token(token: str) -> Optional[dict]:
    """
    Verify and decode a JWT token.
    Returns the token payload if valid, None otherwise.
    
    The payload contains:
    - sub: user mobile number
    - user_id: user database ID
    - role: user role (admin, driver, customer)
    - type: token type (access, refresh)
    - exp: expiration timestamp
    """
    try:
        payload = decode_access_token(token)
        return payload
    except Exception:
        return None
