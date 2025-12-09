from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class TruckLocation(Base):
    __tablename__ = "truck_locations"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=True)  # GPS accuracy in meters
    speed = Column(Float, nullable=True)  # Speed in km/h
    heading = Column(Float, nullable=True)  # Heading in degrees (0-360)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    driver = relationship("User", back_populates="truck_locations")
