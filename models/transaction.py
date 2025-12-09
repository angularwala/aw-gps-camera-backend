from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    amount = Column(Float, nullable=False)
    paid = Column(Float, default=0.0)
    due = Column(Float, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    is_payment = Column(Boolean, default=False)  # True if payment, False if order
    
    # Relationships
    customer = relationship("Customer", back_populates="transactions")
    order = relationship("Order", back_populates="transactions")
