from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db
from models.receipt_settings import ReceiptSettings
from models.user import User
from utils.auth_dependency import get_current_admin
import os
import shutil

router = APIRouter(prefix="/api/receipt-settings", tags=["Receipt Settings"])

UPLOAD_DIR = "uploads/logos"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class ReceiptSettingsResponse(BaseModel):
    id: int
    company_name: str
    company_address: Optional[str]
    company_phone: Optional[str]
    company_email: Optional[str]
    gst_number: Optional[str]
    pan_number: Optional[str]
    bank_name: Optional[str]
    bank_account: Optional[str]
    bank_ifsc: Optional[str]
    upi_id: Optional[str]
    footer_text: Optional[str]
    logo_url: Optional[str]
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ReceiptSettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_ifsc: Optional[str] = None
    upi_id: Optional[str] = None
    footer_text: Optional[str] = None


@router.get("/", response_model=ReceiptSettingsResponse)
def get_receipt_settings(db: Session = Depends(get_db)):
    """Get current receipt header settings"""
    settings = db.query(ReceiptSettings).first()
    if not settings:
        settings = ReceiptSettings(company_name="Yadav Diesel Delivery")
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.put("/", response_model=ReceiptSettingsResponse)
def update_receipt_settings(
    request: ReceiptSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update receipt header settings (Admin only)"""
    settings = db.query(ReceiptSettings).first()
    if not settings:
        settings = ReceiptSettings(company_name="Yadav Diesel Delivery")
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    if request.company_name is not None:
        settings.company_name = request.company_name
    if request.company_address is not None:
        settings.company_address = request.company_address
    if request.company_phone is not None:
        settings.company_phone = request.company_phone
    if request.company_email is not None:
        settings.company_email = request.company_email
    if request.gst_number is not None:
        settings.gst_number = request.gst_number
    if request.pan_number is not None:
        settings.pan_number = request.pan_number
    if request.bank_name is not None:
        settings.bank_name = request.bank_name
    if request.bank_account is not None:
        settings.bank_account = request.bank_account
    if request.bank_ifsc is not None:
        settings.bank_ifsc = request.bank_ifsc
    if request.upi_id is not None:
        settings.upi_id = request.upi_id
    if request.footer_text is not None:
        settings.footer_text = request.footer_text
    
    db.commit()
    db.refresh(settings)
    return settings


@router.post("/logo", response_model=ReceiptSettingsResponse)
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Upload company logo for receipts (Admin only)"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    settings = db.query(ReceiptSettings).first()
    if not settings:
        settings = ReceiptSettings(company_name="Yadav Diesel Delivery")
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    file_extension = os.path.splitext(file.filename)[1]
    filename = f"logo_{datetime.now().timestamp()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    if settings.logo_url:
        old_path = f".{settings.logo_url}"
        if os.path.exists(old_path):
            os.remove(old_path)
    
    settings.logo_url = f"/uploads/logos/{filename}"
    db.commit()
    db.refresh(settings)
    
    return settings
