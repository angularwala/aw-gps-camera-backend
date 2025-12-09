from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class PriceSettings(Base):
    __tablename__ = "price_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    current_rate = Column(Numeric(10, 2), nullable=False, default=91.55)
    effective_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    user = relationship("User", backref="price_updates")
