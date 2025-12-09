from sqlalchemy.orm import Session
from models.user import User, UserRole
from models.customer import Customer
from utils.security import (
    verify_password, get_password_hash, create_access_token, 
    create_refresh_token, decode_refresh_token, validate_password_strength
)
from datetime import timedelta
from config import settings
from typing import Optional, Tuple, Dict
import logging

logger = logging.getLogger(__name__)

class AuthService:
    @staticmethod
    def authenticate_user(db: Session, mobile: str, password: str) -> Optional[User]:
        """Authenticate user with mobile and password"""
        user = db.query(User).filter(User.mobile == mobile).first()
        if not user:
            logger.warning(f"Login attempt with non-existent mobile: {mobile[:4]}****")
            return None
        if not verify_password(password, user.password_hash):
            logger.warning(f"Failed login attempt for user: {user.id}")
            return None
        logger.info(f"Successful login for user: {user.id}")
        return user
    
    @staticmethod
    def create_user(
        db: Session, 
        name: str, 
        mobile: str, 
        password: str, 
        role: UserRole, 
        company_name: Optional[str] = None, 
        address: Optional[str] = None, 
        gps_lat: Optional[float] = None, 
        gps_long: Optional[float] = None
    ) -> Optional[User]:
        """Create a new user with password strength validation"""
        existing_user = db.query(User).filter(User.mobile == mobile).first()
        if existing_user:
            return None
        
        hashed_password = get_password_hash(password)
        user = User(
            name=name,
            mobile=mobile,
            password_hash=hashed_password,
            role=role
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        if role == UserRole.CUSTOMER and company_name:
            customer = Customer(
                user_id=user.id,
                company_name=company_name,
                address=address,
                gps_lat=gps_lat,
                gps_long=gps_long
            )
            db.add(customer)
            db.commit()
        
        logger.info(f"New user created: {user.id} with role: {role.value}")
        return user
    
    @staticmethod
    def generate_tokens(user: User) -> Dict[str, str]:
        """Generate both access and refresh tokens"""
        token_data = {
            "sub": user.mobile, 
            "role": user.role.value, 
            "user_id": user.id
        }
        
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(data=token_data, expires_delta=access_token_expires)
        refresh_token = create_refresh_token(data=token_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token
        }
    
    @staticmethod
    def generate_token(user: User) -> str:
        """Generate access token only (legacy support)"""
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": user.mobile, "role": user.role.value, "user_id": user.id},
            expires_delta=access_token_expires
        )
        return access_token
    
    @staticmethod
    def refresh_access_token(db: Session, refresh_token: str) -> Optional[Dict[str, str]]:
        """Refresh access token using refresh token"""
        payload = decode_refresh_token(refresh_token)
        if not payload:
            logger.warning("Invalid refresh token attempted")
            return None
        
        mobile = payload.get("sub")
        user = db.query(User).filter(User.mobile == mobile).first()
        if not user:
            logger.warning(f"Refresh token for non-existent user: {mobile[:4] if mobile else '****'}****")
            return None
        
        return AuthService.generate_tokens(user)
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using secure algorithm"""
        return get_password_hash(password)
    
    @staticmethod
    def verify_password_strength(password: str) -> Tuple[bool, str]:
        """Validate password meets security requirements"""
        return validate_password_strength(password)
