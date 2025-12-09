"""
Logs viewing endpoints for admin dashboard
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from database import get_db
from models.log import SystemLog, ApiLog, ErrorLog, UserActivityLog
from models.user import User
from utils.auth_dependency import get_current_user

router = APIRouter(prefix="/api/logs", tags=["Logs"])

class LogResponse(BaseModel):
    id: int
    log_type: str
    level: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[str] = None
    message: Optional[str] = None
    error_message: Optional[str] = None
    action: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    status_code: Optional[int] = None
    duration_ms: Optional[int] = None
    ip_address: Optional[str] = None
    user_id: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

@router.get("/all", response_model=List[LogResponse])
def get_all_logs(
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all logs (system, api, error, activity) combined
    Admin only endpoint
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    all_logs = []
    
    # Get system logs
    system_logs = db.query(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit).all()
    for log in system_logs:
        all_logs.append({
            "id": log.id,
            "log_type": "system",
            "level": log.level,
            "category": log.category,
            "message": log.message,
            "ip_address": log.ip_address,
            "user_id": log.user_id,
            "created_at": log.created_at
        })
    
    # Get API logs
    api_logs = db.query(ApiLog).order_by(desc(ApiLog.created_at)).limit(limit).all()
    for log in api_logs:
        all_logs.append({
            "id": log.id,
            "log_type": "api",
            "endpoint": log.endpoint,
            "method": log.method,
            "status_code": log.status_code,
            "duration_ms": log.duration_ms,
            "ip_address": log.ip_address,
            "user_id": log.user_id,
            "created_at": log.created_at
        })
    
    # Get error logs
    error_logs = db.query(ErrorLog).order_by(desc(ErrorLog.created_at)).limit(limit).all()
    for log in error_logs:
        all_logs.append({
            "id": log.id,
            "log_type": "error",
            "severity": log.severity,
            "error_message": log.error_message,
            "endpoint": log.endpoint,
            "user_id": log.user_id,
            "created_at": log.created_at
        })
    
    # Get user activity logs
    activity_logs = db.query(UserActivityLog).order_by(desc(UserActivityLog.created_at)).limit(limit).all()
    for log in activity_logs:
        all_logs.append({
            "id": log.id,
            "log_type": "activity",
            "action": log.action,
            "description": log.description,
            "ip_address": log.ip_address,
            "user_id": log.user_id,
            "created_at": log.created_at
        })
    
    # Sort by created_at descending
    all_logs.sort(key=lambda x: x["created_at"], reverse=True)
    
    # Limit to requested number
    return all_logs[:limit]

@router.get("/system", response_model=List[LogResponse])
def get_system_logs(
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get system logs"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    logs = db.query(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit).all()
    return [
        {
            "id": log.id,
            "log_type": "system",
            "level": log.level,
            "category": log.category,
            "message": log.message,
            "ip_address": log.ip_address,
            "user_id": log.user_id,
            "created_at": log.created_at
        }
        for log in logs
    ]

@router.get("/errors", response_model=List[LogResponse])
def get_error_logs(
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get error logs"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    logs = db.query(ErrorLog).order_by(desc(ErrorLog.created_at)).limit(limit).all()
    return [
        {
            "id": log.id,
            "log_type": "error",
            "severity": log.severity,
            "error_message": log.error_message,
            "endpoint": log.endpoint,
            "user_id": log.user_id,
            "created_at": log.created_at
        }
        for log in logs
    ]

@router.get("/activity", response_model=List[LogResponse])
def get_activity_logs(
    limit: int = 200,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user activity logs"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    query = db.query(UserActivityLog)
    if user_id:
        query = query.filter(UserActivityLog.user_id == user_id)
    
    logs = query.order_by(desc(UserActivityLog.created_at)).limit(limit).all()
    return [
        {
            "id": log.id,
            "log_type": "activity",
            "action": log.action,
            "description": log.description,
            "ip_address": log.ip_address,
            "user_id": log.user_id,
            "created_at": log.created_at
        }
        for log in logs
    ]
