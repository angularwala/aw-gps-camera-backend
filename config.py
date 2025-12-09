import os
from pydantic_settings import BaseSettings
import hashlib

def _derive_key(base_secret: str, purpose: str) -> str:
    """Derive a deterministic key from base secret for specific purpose"""
    return hashlib.sha256(f"{base_secret}:{purpose}".encode()).hexdigest()

class Settings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL", "")
    _base_secret: str = os.getenv("SESSION_SECRET", "default-dev-secret-change-in-production")
    
    @property
    def secret_key(self) -> str:
        """JWT access token signing key"""
        return self._base_secret
    
    @property
    def refresh_secret_key(self) -> str:
        """JWT refresh token signing key - derived from base secret"""
        return _derive_key(self._base_secret, "refresh_token")
    
    @property
    def password_pepper(self) -> str:
        """Password pepper - derived from base secret"""
        return _derive_key(self._base_secret, "password_pepper")[:32]
    
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours for access token (mobile app convenience)
    refresh_token_expire_days: int = 30  # 30 days (1 month) for refresh token
    
    min_password_length: int = 6
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15
    
    cors_origins: list = ["*"]
    
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    auth_rate_limit_requests: int = 5
    auth_rate_limit_window_seconds: int = 60
    
    class Config:
        env_file = ".env"

settings = Settings()
