from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import Optional
from database import Base

class ReceiptSettings(Base):
    __tablename__ = "receipt_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False, default="Yadav Diesel Delivery")
    company_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    company_email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gst_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    pan_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    bank_ifsc: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    upi_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    footer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
