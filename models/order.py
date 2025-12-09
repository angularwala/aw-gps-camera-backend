from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import enum

class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    liters = Column(Float, nullable=False)
    rate = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    delivery_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    otp = Column(String(6), nullable=True)
    signature = Column(String(500), nullable=True)
    
    delivery_address = Column(String(500), nullable=True)
    delivery_gps_lat = Column(Float, nullable=True)
    delivery_gps_long = Column(Float, nullable=True)
    vehicle_number = Column(String(50), nullable=True)
    vehicle_photo = Column(String(500), nullable=True)
    contact_number = Column(String(20), nullable=True)
    
    # Relationships
    customer = relationship("Customer", back_populates="orders")
    driver = relationship("User", foreign_keys=[driver_id])
    receipts = relationship("Receipt", back_populates="order")
    transactions = relationship("Transaction", back_populates="order")
