from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import os
import shutil
from pathlib import Path
from database import get_db
from services.auth_service import AuthService
from utils.auth_dependency import get_current_user
from models.user import User
from models.customer import Customer

router = APIRouter(prefix="/api/profile", tags=["Profile"])

UPLOAD_DIR = Path("uploads/profile_photos")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    company_name: Optional[str] = None
    address: Optional[str] = None

class ProfileResponse(BaseModel):
    id: int
    name: str
    mobile: str
    role: str
    profile_photo: Optional[str] = None
    company_name: Optional[str] = None
    address: Optional[str] = None
    
    class Config:
        from_attributes = True

@router.post("/upload-photo")
async def upload_profile_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload profile photo for current user"""
    
    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Read file content to check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024*1024)}MB"
        )
    
    # Generate unique filename
    filename = f"{current_user.id}_{current_user.role.value}{file_ext}"
    file_path = UPLOAD_DIR / filename
    
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    
    # Update user profile_photo in database
    relative_path = f"uploads/profile_photos/{filename}"
    current_user.profile_photo = relative_path
    
    # If user is a customer, also update customer profile_photo
    if current_user.role.value == "customer" and current_user.customer:
        current_user.customer.profile_photo = relative_path
    
    db.commit()
    db.refresh(current_user)
    
    return {
        "message": "Profile photo uploaded successfully",
        "profile_photo": relative_path
    }

@router.delete("/delete-photo")
def delete_profile_photo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete profile photo for current user"""
    
    if not current_user.profile_photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile photo found"
        )
    
    # Delete file from filesystem
    file_path = Path(current_user.profile_photo)
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception as e:
            # Log error but continue to remove from database
            print(f"Error deleting file: {str(e)}")
    
    # Remove from database
    current_user.profile_photo = None
    if current_user.role.value == "customer" and current_user.customer:
        current_user.customer.profile_photo = None
    
    db.commit()
    
    return {"message": "Profile photo deleted successfully"}

@router.get("/me", response_model=ProfileResponse)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current user's profile"""
    
    response_data = {
        "id": current_user.id,
        "name": current_user.name,
        "mobile": current_user.mobile,
        "role": current_user.role.value,
        "profile_photo": current_user.profile_photo
    }
    
    # Add customer-specific fields if user is a customer
    if current_user.role.value == "customer" and current_user.customer:
        response_data["company_name"] = current_user.customer.company_name
        response_data["address"] = current_user.customer.address
    
    return response_data

@router.put("/update", response_model=ProfileResponse)
def update_profile(
    update_data: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update current user's profile"""
    
    # Update user name if provided
    if update_data.name:
        current_user.name = update_data.name.strip()
    
    # Update customer-specific fields if user is a customer
    if current_user.role.value == "customer" and current_user.customer:
        if update_data.company_name is not None:
            current_user.customer.company_name = update_data.company_name.strip()
        if update_data.address is not None:
            current_user.customer.address = update_data.address.strip()
    
    db.commit()
    db.refresh(current_user)
    
    return get_profile(db, current_user)
