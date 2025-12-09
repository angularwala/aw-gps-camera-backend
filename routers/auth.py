from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, validator, Field
from typing import List, Optional
from datetime import datetime
from database import get_db
from services.auth_service import AuthService
from models.user import UserRole, User, Language
from utils.auth_dependency import get_current_user
import re

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    mobile: str = Field(..., min_length=10, max_length=15, description="Mobile number (10-15 digits)")
    password: str = Field(..., min_length=6, max_length=100, description="Password (minimum 6 characters)")
    
    @validator('mobile')
    def validate_mobile(cls, v):
        # Remove whitespace
        v = v.strip()
        # Check if mobile contains only digits and optional + prefix
        if not re.match(r'^\+?[0-9]{10,15}$', v):
            raise ValueError('Invalid mobile number format. Use 10-15 digits with optional + prefix')
        # Normalize by removing + prefix for consistent storage
        v = v.lstrip('+')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters long')
        # Basic XSS prevention
        if re.search(r'<\s*script|javascript:', v, re.IGNORECASE):
            raise ValueError('Invalid characters in password')
        return v

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full name (2-100 characters)")
    mobile: str = Field(..., min_length=10, max_length=15, description="Mobile number (10-15 digits)")
    password: str = Field(..., min_length=6, max_length=100, description="Password (minimum 6 characters)")
    role: UserRole = UserRole.CUSTOMER
    company_name: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    gps_lat: Optional[float] = Field(None, ge=-90, le=90)
    gps_long: Optional[float] = Field(None, ge=-180, le=180)
    
    @validator('name')
    def validate_name(cls, v):
        # Remove excessive whitespace
        v = ' '.join(v.split())
        if len(v) < 2:
            raise ValueError('Name must be at least 2 characters')
        # Basic XSS prevention
        if re.search(r'<\s*script|<\s*iframe|javascript:', v, re.IGNORECASE):
            raise ValueError('Invalid characters in name')
        # Allow Unicode letters (supports Hindi, Marathi, Tamil, etc.), spaces, and common name characters
        if not re.match(r'^[\w\s\'\-\.]+$', v, re.UNICODE):
            raise ValueError('Name contains invalid characters')
        return v
    
    @validator('mobile')
    def validate_mobile(cls, v):
        v = v.strip()
        if not re.match(r'^\+?[0-9]{10,15}$', v):
            raise ValueError('Invalid mobile number format. Use 10-15 digits with optional + prefix')
        # Normalize by removing + prefix for consistent storage and lookup
        v = v.lstrip('+')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters long')
        # Check for at least one letter and one number for stronger passwords
        if not re.search(r'[A-Za-z]', v) or not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one letter and one number')
        # Basic XSS prevention
        if re.search(r'<\s*script|javascript:', v, re.IGNORECASE):
            raise ValueError('Invalid characters in password')
        return v
    
    @validator('company_name')
    def validate_company_name(cls, v):
        if v is not None:
            v = ' '.join(v.split())
            # Basic XSS prevention
            if re.search(r'<\s*script|<\s*iframe|javascript:', v, re.IGNORECASE):
                raise ValueError('Invalid characters in company name')
        return v
    
    @validator('address')
    def validate_address(cls, v):
        if v is not None:
            v = ' '.join(v.split())
            # Basic XSS prevention
            if re.search(r'<\s*script|<\s*iframe|javascript:', v, re.IGNORECASE):
                raise ValueError('Invalid characters in address')
        return v

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    user_id: int
    name: str
    role: str
    customer_id: Optional[int] = None
    profile_photo: Optional[str] = None
    base_language: str = "english"
    second_language: Optional[str] = None
    second_language_enabled: bool = False
    expires_in: int = 3600

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20, description="Refresh token to exchange for new access token")

class UserResponse(BaseModel):
    id: int
    name: str
    mobile: str
    role: str
    profile_photo: Optional[str] = None
    base_language: str = "english"
    second_language: Optional[str] = None
    second_language_enabled: bool = False
    
    class Config:
        from_attributes = True

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = AuthService.authenticate_user(db, request.mobile, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect mobile number or password"
        )
    
    tokens = AuthService.generate_tokens(user)
    
    customer_id = None
    if user.role == UserRole.CUSTOMER and user.customer:
        customer_id = user.customer.id
    
    from config import settings
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        user_id=user.id,
        name=user.name,
        role=user.role.value,
        customer_id=customer_id,
        profile_photo=user.profile_photo,
        base_language=user.base_language.value if user.base_language else "english",
        second_language=user.second_language.value if user.second_language else None,
        second_language_enabled=user.second_language_enabled if user.second_language_enabled is not None else False,
        expires_in=settings.access_token_expire_minutes * 60
    )

@router.post("/refresh", response_model=TokenResponse)
def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Exchange refresh token for new access token"""
    tokens = AuthService.refresh_access_token(db, request.refresh_token)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    from utils.security import decode_refresh_token
    payload = decode_refresh_token(request.refresh_token)
    user = db.query(User).filter(User.mobile == payload.get("sub")).first()
    
    customer_id = None
    if user and user.role == UserRole.CUSTOMER and user.customer:
        customer_id = user.customer.id
    
    from config import settings
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        user_id=user.id if user else 0,
        name=user.name if user else "",
        role=user.role.value if user else "",
        customer_id=customer_id,
        profile_photo=user.profile_photo if user else None,
        base_language=user.base_language.value if user and user.base_language else "english",
        second_language=user.second_language.value if user and user.second_language else None,
        second_language_enabled=user.second_language_enabled if user and user.second_language_enabled is not None else False,
        expires_in=settings.access_token_expire_minutes * 60
    )

@router.post("/register", response_model=TokenResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    user = AuthService.create_user(
        db=db,
        name=request.name,
        mobile=request.mobile,
        password=request.password,
        role=request.role,
        company_name=request.company_name,
        address=request.address,
        gps_lat=request.gps_lat,
        gps_long=request.gps_long
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mobile number already registered"
        )
    
    tokens = AuthService.generate_tokens(user)
    
    customer_id = None
    if user.role == UserRole.CUSTOMER and user.customer:
        customer_id = user.customer.id
    
    from config import settings
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        user_id=user.id,
        name=user.name,
        role=user.role.value,
        customer_id=customer_id,
        profile_photo=user.profile_photo,
        base_language=user.base_language.value if user.base_language else "english",
        second_language=user.second_language.value if user.second_language else None,
        second_language_enabled=user.second_language_enabled if user.second_language_enabled is not None else False,
        expires_in=settings.access_token_expire_minutes * 60
    )

@router.get("/users", response_model=List[UserResponse])
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        UserResponse(
            id=user.id,
            name=user.name,
            mobile=user.mobile,
            role=user.role.value,
            profile_photo=user.profile_photo,
            base_language=user.base_language.value if user.base_language else "english",
            second_language=user.second_language.value if user.second_language else None,
            second_language_enabled=user.second_language_enabled if user.second_language_enabled is not None else False
        )
        for user in users
    ]

@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}


class AdminResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str = Field(..., min_length=6, max_length=100)
    
    @validator('new_password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters long')
        if not re.search(r'[A-Za-z]', v) or not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one letter and one number')
        if re.search(r'<\s*script|javascript:', v, re.IGNORECASE):
            raise ValueError('Invalid characters in password')
        return v


@router.post("/admin/reset-password")
def admin_reset_password(request: AdminResetPasswordRequest, db: Session = Depends(get_db)):
    """Admin endpoint to reset password for any customer or driver"""
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot reset admin password through this endpoint"
        )
    
    hashed_password = AuthService.hash_password(request.new_password)
    user.password_hash = hashed_password
    db.commit()
    
    return {
        "message": "Password reset successfully",
        "user_id": user.id,
        "user_name": user.name,
        "role": user.role.value
    }


@router.get("/users/customers-and-drivers", response_model=List[UserResponse])
def get_customers_and_drivers(db: Session = Depends(get_db)):
    """Get all customers and drivers for password management"""
    users = db.query(User).filter(
        User.role.in_([UserRole.CUSTOMER, UserRole.DRIVER])
    ).all()
    return [
        UserResponse(
            id=user.id,
            name=user.name,
            mobile=user.mobile,
            role=user.role.value,
            profile_photo=user.profile_photo,
            base_language=user.base_language.value if user.base_language else "english",
            second_language=user.second_language.value if user.second_language else None,
            second_language_enabled=user.second_language_enabled if user.second_language_enabled is not None else False
        )
        for user in users
    ]


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    mobile: Optional[str] = None


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, request: UserUpdateRequest, db: Session = Depends(get_db)):
    """Update user details (Admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if request.name is not None:
        user.name = request.name
    if request.mobile is not None:
        existing = db.query(User).filter(User.mobile == request.mobile, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Mobile number already in use")
        user.mobile = request.mobile
    
    db.commit()
    db.refresh(user)
    
    return UserResponse(
        id=user.id,
        name=user.name,
        mobile=user.mobile,
        role=user.role.value,
        profile_photo=user.profile_photo,
        base_language=user.base_language.value if user.base_language else "english",
        second_language=user.second_language.value if user.second_language else None,
        second_language_enabled=user.second_language_enabled if user.second_language_enabled is not None else False
    )


class FCMTokenRequest(BaseModel):
    fcm_token: str = Field(..., min_length=10, max_length=500, description="Firebase Cloud Messaging token")


@router.post("/fcm-token")
def register_fcm_token(
    request: FCMTokenRequest, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Register or update FCM token for push notifications.
    Called by the mobile app after login to enable push notifications.
    """
    current_user.fcm_token = request.fcm_token
    db.commit()
    
    return {
        "message": "FCM token registered successfully",
        "user_id": current_user.id,
        "role": current_user.role.value
    }


@router.delete("/fcm-token")
def remove_fcm_token(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Remove FCM token when user logs out.
    Prevents notifications from being sent to logged-out devices.
    """
    current_user.fcm_token = None
    db.commit()
    
    return {"message": "FCM token removed successfully"}
