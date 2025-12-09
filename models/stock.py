from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import enum

class StockTransactionType(str, enum.Enum):
    STOCK_IN = "stock_in"
    STOCK_OUT = "stock_out"

class StockTransaction(Base):
    __tablename__ = "stock_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    transaction_type = Column(Enum(StockTransactionType), nullable=False)
    liters = Column(Numeric(10, 2), nullable=False)
    rate_per_liter = Column(Numeric(10, 2), nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=True)
    supplier_name = Column(String(200), nullable=True)
    vehicle_number = Column(String(50), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    notes = Column(Text, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    transaction_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    order = relationship("Order", backref="stock_transactions")
    user = relationship("User", backref="stock_transactions")


class CurrentStock(Base):
    __tablename__ = "current_stock"
    
    id = Column(Integer, primary_key=True, index=True)
    total_liters = Column(Numeric(12, 2), default=0, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
