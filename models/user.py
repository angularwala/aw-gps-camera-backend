from sqlalchemy import String, Enum as SQLEnum, Boolean, DateTime
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from database import Base
import enum

if TYPE_CHECKING:
    from models.customer import Customer
    from models.truck_location import TruckLocation
    from models.vehicle_tracking import VehicleOdometer

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    DRIVER = "driver"
    CUSTOMER = "customer"

class Language(str, enum.Enum):
    english = "english"
    marathi = "marathi"
    hindi = "hindi"
    gujarati = "gujarati"
    tamil = "tamil"
    kannada = "kannada"

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    mobile: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), nullable=False)
    profile_photo: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Language preferences
    base_language: Mapped[Language] = mapped_column(SQLEnum(Language), nullable=False, default=Language.english, server_default='english')
    second_language: Mapped[Optional[Language]] = mapped_column(SQLEnum(Language), nullable=True)
    second_language_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='false')
    
    # Push notification token (FCM)
    fcm_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    customer: Mapped[Optional["Customer"]] = relationship("Customer", back_populates="user", uselist=False)
    truck_locations: Mapped[List["TruckLocation"]] = relationship("TruckLocation", back_populates="driver")
    vehicle_tracking: Mapped[List["VehicleOdometer"]] = relationship("VehicleOdometer", back_populates="driver")
