from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from database import get_db
from models.user import User, Language, UserRole
from utils.auth_dependency import get_current_admin

router = APIRouter(prefix="/api/language-settings", tags=["Language Settings"])

class UpdateLanguagePreferencesRequest(BaseModel):
    user_id: int
    base_language: Optional[str] = None
    second_language: Optional[str] = None
    second_language_enabled: Optional[bool] = None

class UserLanguageResponse(BaseModel):
    id: int
    name: str
    mobile: str
    role: str
    base_language: str
    second_language: Optional[str]
    second_language_enabled: bool
    
    class Config:
        from_attributes = True

@router.get("/users", response_model=List[UserLanguageResponse])
def get_all_users_with_languages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all users with their language preferences (Admin only)"""
    users = db.query(User).filter(User.role.in_([UserRole.CUSTOMER, UserRole.DRIVER, UserRole.ADMIN])).all()
    return [
        UserLanguageResponse(
            id=user.id,
            name=user.name,
            mobile=user.mobile,
            role=user.role.value,
            base_language=user.base_language.value if user.base_language else "english",
            second_language=user.second_language.value if user.second_language else None,
            second_language_enabled=user.second_language_enabled if user.second_language_enabled is not None else False
        )
        for user in users
    ]

@router.patch("/update", response_model=UserLanguageResponse)
def update_user_language_preferences(
    request: UpdateLanguagePreferencesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update language preferences for a specific user (Admin only)"""
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update language preferences
    if request.base_language is not None:
        try:
            user.base_language = Language(request.base_language.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid base language. Must be one of: {', '.join([l.value for l in Language])}"
            )
    
    if request.second_language is not None:
        if request.second_language == "":
            user.second_language = None
        else:
            try:
                user.second_language = Language(request.second_language.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid second language. Must be one of: {', '.join([l.value for l in Language])}"
                )
    
    if request.second_language_enabled is not None:
        user.second_language_enabled = request.second_language_enabled
    
    db.commit()
    db.refresh(user)
    
    return UserLanguageResponse(
        id=user.id,
        name=user.name,
        mobile=user.mobile,
        role=user.role.value,
        base_language=user.base_language.value if user.base_language else "english",
        second_language=user.second_language.value if user.second_language else None,
        second_language_enabled=user.second_language_enabled if user.second_language_enabled is not None else False
    )

@router.get("/languages", response_model=List[str])
def get_available_languages():
    """Get list of all available languages"""
    return [lang.value for lang in Language]
