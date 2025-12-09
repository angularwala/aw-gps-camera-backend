from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import enum

class LogLevel(str, enum.Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class LogCategory(str, enum.Enum):
    API_REQUEST = "api_request"
    API_RESPONSE = "api_response"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    ORDER_MANAGEMENT = "order_management"
    FILE_UPLOAD = "file_upload"
    LOCATION_UPDATE = "location_update"
    SYSTEM = "system"
    USER_ACTION = "user_action"

class SystemLog(Base):
    """General system logs for all application events"""
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    level = Column(SQLEnum(LogLevel), nullable=False, index=True)
    category = Column(SQLEnum(LogCategory), nullable=False, index=True)
    message = Column(Text, nullable=False)
    details = Column(Text, nullable=True)  # JSON string for additional data
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationship
    user = relationship("User", foreign_keys=[user_id])

class ApiLog(Base):
    """API request/response logs"""
    __tablename__ = "api_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    method = Column(String(10), nullable=False)  # GET, POST, PUT, DELETE
    endpoint = Column(String(500), nullable=False, index=True)
    status_code = Column(Integer, nullable=False, index=True)
    request_body = Column(Text, nullable=True)
    response_body = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    ip_address = Column(String(50), nullable=True)
    duration_ms = Column(Integer, nullable=True)  # Request duration in milliseconds
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationship
    user = relationship("User", foreign_keys=[user_id])

class ErrorLog(Base):
    """Error and exception logs"""
    __tablename__ = "error_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    error_type = Column(String(200), nullable=False, index=True)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    endpoint = Column(String(500), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    request_data = Column(Text, nullable=True)
    severity = Column(SQLEnum(LogLevel), default=LogLevel.ERROR, nullable=False)
    resolved = Column(String(10), default="false", nullable=False)  # "true" or "false"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationship
    user = relationship("User", foreign_keys=[user_id])

class UserActivityLog(Base):
    """User activity and action logs"""
    __tablename__ = "user_activity_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(200), nullable=False, index=True)  # login, logout, place_order, upload_receipt, etc.
    description = Column(Text, nullable=True)
    entity_type = Column(String(100), nullable=True)  # order, receipt, customer, etc.
    entity_id = Column(Integer, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationship
    user = relationship("User", foreign_keys=[user_id])
