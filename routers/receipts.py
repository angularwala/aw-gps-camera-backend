from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from database import get_db
from models.receipt import Receipt
from models.order import Order
from models.user import User
from utils.auth_dependency import get_current_user
import os
import shutil

router = APIRouter(prefix="/api/receipts", tags=["Receipts"])

# Create uploads directory
UPLOAD_DIR = "uploads/receipts"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class ReceiptResponse(BaseModel):
    id: int
    order_id: int
    file_url: str
    file_type: Optional[str]
    timestamp: datetime
    
    class Config:
        from_attributes = True

@router.get("/", response_model=List[ReceiptResponse])
def get_receipts(order_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Receipt)
    if order_id:
        query = query.filter(Receipt.order_id == order_id)
    receipts = query.order_by(Receipt.timestamp.desc()).all()
    return receipts

@router.post("/upload")
async def upload_receipt(
    order_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Generate unique filename
    file_extension = os.path.splitext(file.filename)[1]
    filename = f"receipt_{order_id}_{datetime.now().timestamp()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Create receipt record
    receipt = Receipt(
        order_id=order_id,
        file_url=f"/uploads/receipts/{filename}",
        file_type=file.content_type
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    
    return ReceiptResponse(
        id=receipt.id,
        order_id=receipt.order_id,
        file_url=receipt.file_url,
        file_type=receipt.file_type,
        timestamp=receipt.timestamp
    )

@router.get("/{receipt_id}", response_model=ReceiptResponse)
def get_receipt(receipt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt

@router.get("/{receipt_id}/download")
def download_receipt(receipt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Download receipt file with proper headers for saving"""
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    
    # Verify user has access to this receipt's order
    order = db.query(Order).filter(Order.id == receipt.order_id).first()
    if order and current_user.role != "admin":
        if current_user.role == "driver" and order.driver_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif current_user.role == "customer" and order.customer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get file path
    file_path = f".{receipt.file_url}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Receipt file not found")
    
    # Extract filename for download
    filename = os.path.basename(receipt.file_url)
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=receipt.file_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/order/{order_id}", response_model=List[ReceiptResponse])
def get_receipts_by_order(order_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all receipts for a specific order with access control"""
    # Verify user has access to this order
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if current_user.role != "admin":
        if current_user.role == "driver" and order.driver_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif current_user.role == "customer" and order.customer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    receipts = db.query(Receipt).filter(Receipt.order_id == order_id).order_by(Receipt.timestamp.desc()).all()
    return receipts

@router.delete("/{receipt_id}")
def delete_receipt(receipt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    
    # Delete file
    file_path = f".{receipt.file_url}"
    if os.path.exists(file_path):
        os.remove(file_path)
    
    db.delete(receipt)
    db.commit()
    
    return {"message": "Receipt deleted successfully"}
