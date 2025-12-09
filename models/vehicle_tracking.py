from sqlalchemy import Column, Integer, Float, Date, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class VehicleOdometer(Base):
    __tablename__ = "vehicle_odometer"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    start_km = Column(Float, nullable=False)
    end_km = Column(Float, nullable=False)
    total_km = Column(Float, nullable=False)
    fuel_consumed = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    driver = relationship("User", back_populates="vehicle_tracking")
    
    def __repr__(self):
        return f"<VehicleOdometer(driver_id={self.driver_id}, date={self.date}, total_km={self.total_km})>"
