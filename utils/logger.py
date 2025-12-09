"""
Comprehensive logging utilities for database logging
"""
from sqlalchemy.orm import Session
from models.log import SystemLog, ApiLog, ErrorLog, UserActivityLog, LogLevel, LogCategory
from database import SessionLocal
from utils.sanitizer import DataSanitizer
import json
from typing import Optional, Dict, Any
from datetime import datetime

class DatabaseLogger:
    """Centralized database logger for all application logging"""
    
    @staticmethod
    def log_system(
        level: LogLevel,
        category: LogCategory,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        db: Optional[Session] = None
    ):
        """Log system events with sensitive data sanitization"""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        
        try:
            # Sanitize details dictionary
            sanitized_details = DataSanitizer.sanitize_dict(details) if details else None
            
            log = SystemLog(
                level=level,
                category=category,
                message=message,
                details=json.dumps(sanitized_details) if sanitized_details else None,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent
            )
            db.add(log)
            db.commit()
        except Exception as e:
            print(f"Failed to write system log: {e}")
            db.rollback()
        finally:
            if should_close:
                db.close()
    
    @staticmethod
    def log_api_request(
        method: str,
        endpoint: str,
        status_code: int,
        request_body: Optional[str] = None,
        response_body: Optional[str] = None,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        duration_ms: Optional[int] = None,
        db: Optional[Session] = None
    ):
        """Log API requests and responses with sensitive data sanitization"""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        
        try:
            # Sanitize request and response bodies to remove sensitive data
            sanitized_request = DataSanitizer.sanitize_json_string(request_body) if request_body else None
            sanitized_response = DataSanitizer.sanitize_json_string(response_body) if response_body else None
            
            log = ApiLog(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                request_body=sanitized_request,
                response_body=sanitized_response,
                user_id=user_id,
                ip_address=ip_address,
                duration_ms=duration_ms
            )
            db.add(log)
            db.commit()
        except Exception as e:
            print(f"Failed to write API log: {e}")
            db.rollback()
        finally:
            if should_close:
                db.close()
    
    @staticmethod
    def log_error(
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        endpoint: Optional[str] = None,
        user_id: Optional[int] = None,
        request_data: Optional[Dict[str, Any]] = None,
        severity: LogLevel = LogLevel.ERROR,
        db: Optional[Session] = None
    ):
        """Log errors and exceptions with sensitive data sanitization"""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        
        try:
            # Sanitize request_data dictionary
            sanitized_request_data = DataSanitizer.sanitize_dict(request_data) if request_data else None
            
            log = ErrorLog(
                error_type=error_type,
                error_message=error_message,
                stack_trace=stack_trace,
                endpoint=endpoint,
                user_id=user_id,
                request_data=json.dumps(sanitized_request_data) if sanitized_request_data else None,
                severity=severity,
                resolved="false"
            )
            db.add(log)
            db.commit()
        except Exception as e:
            print(f"Failed to write error log: {e}")
            db.rollback()
        finally:
            if should_close:
                db.close()
    
    @staticmethod
    def log_user_activity(
        user_id: int,
        action: str,
        description: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        db: Optional[Session] = None
    ):
        """Log user activities with sensitive data sanitization"""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        
        try:
            # Sanitize description to remove sensitive information
            sanitized_description = DataSanitizer.sanitize_string(description) if description else None
            
            log = UserActivityLog(
                user_id=user_id,
                action=action,
                description=sanitized_description,
                entity_type=entity_type,
                entity_id=entity_id,
                ip_address=ip_address
            )
            db.add(log)
            db.commit()
        except Exception as e:
            print(f"Failed to write user activity log: {e}")
            db.rollback()
        finally:
            if should_close:
                db.close()

# Convenience functions
def log_info(message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs):
    """Log INFO level message"""
    DatabaseLogger.log_system(LogLevel.INFO, category, message, **kwargs)

def log_warning(message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs):
    """Log WARNING level message"""
    DatabaseLogger.log_system(LogLevel.WARNING, category, message, **kwargs)

def log_error(message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs):
    """Log ERROR level message"""
    DatabaseLogger.log_system(LogLevel.ERROR, category, message, **kwargs)

def log_debug(message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs):
    """Log DEBUG level message"""
    DatabaseLogger.log_system(LogLevel.DEBUG, category, message, **kwargs)
