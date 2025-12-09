from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum

class NotificationType(str, enum.Enum):
    # Customer notifications
    ORDER_INITIATED = "order_initiated"
    DRIVER_ASSIGNED = "driver_assigned"
    ORDER_IN_TRANSIT = "order_in_transit"
    ORDER_DELIVERED = "order_delivered"
    ORDER_CANCELLED = "order_cancelled"
    
    # Admin notifications
    NEW_ORDER = "new_order"
    DELIVERY_STARTED = "delivery_started"
    DELIVERY_COMPLETED = "delivery_completed"
    PAYMENT_RECEIVED = "payment_received"
    LOW_STOCK = "low_stock"
    
    # Driver notifications
    ORDER_ASSIGNED = "order_assigned"
    ORDER_UNASSIGNED = "order_unassigned"
    PAYMENT_CONFIRMED = "payment_confirmed"

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    DRIVER = "driver"
    CUSTOMER = "customer"

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # NULL for broadcast
    role = Column(Enum(UserRole), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    type = Column(Enum(NotificationType), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    extra_data = Column(JSON, nullable=True)  # Extra data like customer_name, amount, etc.
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", backref="notifications")
    order = relationship("Order", backref="notifications")
    
    def __repr__(self):
        return f"<Notification {self.type} for {self.role}>"
