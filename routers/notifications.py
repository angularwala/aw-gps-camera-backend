from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging

from database import get_db
from models import Notification, NotificationType, UserRole
from services.notification_service import NotificationService
from services.notification_broadcast import notification_manager
from utils.auth_dependency import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

class NotificationResponse(BaseModel):
    id: int
    user_id: Optional[int]
    role: str
    order_id: Optional[int]
    type: str
    title: str
    message: str
    extra_data: Optional[dict]
    is_read: bool
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class MarkReadRequest(BaseModel):
    notification_ids: List[int]

@router.get("/", response_model=List[NotificationResponse])
def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get notifications for the current user (user-specific + role-broadcast)"""
    notifications = NotificationService.get_user_notifications(
        db, 
        user_id=current_user.id,
        user_role=current_user.role,
        unread_only=unread_only,
        limit=limit
    )
    return notifications

@router.get("/unread-count")
def get_unread_count(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get count of unread notifications"""
    count = NotificationService.get_unread_count(
        db, 
        current_user.id,
        current_user.role
    )
    return {"count": count}

@router.patch("/{notification_id}/read")
def mark_notification_as_read(
    notification_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a specific notification as read"""
    success = NotificationService.mark_as_read(
        db, 
        notification_id, 
        current_user.id,
        current_user.role
    )
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found or access denied")
    return {"message": "Notification marked as read"}

@router.patch("/mark-all-read")
def mark_all_notifications_as_read(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark all user-specific notifications as read (excludes role-broadcast notifications)"""
    count = NotificationService.mark_all_as_read(
        db, 
        current_user.id,
        current_user.role
    )
    return {"message": f"{count} notifications marked as read"}

@router.websocket("/ws")
async def notifications_websocket(
    websocket: WebSocket, 
    token: str = Query(...)
):
    """
    WebSocket endpoint for real-time notification updates.
    Connect with token query parameter for authentication.
    Receives new notifications in real-time.
    """
    from utils.auth import verify_token
    from contextlib import contextmanager
    
    @contextmanager
    def get_db_session():
        db = next(get_db())
        try:
            yield db
        finally:
            db.close()
    
    try:
        payload = verify_token(token)
        if not payload or "user_id" not in payload:
            await websocket.close(code=1008, reason="Invalid authentication token")
            return
        
        user_id = payload.get("user_id")
        user_role = payload.get("role", "customer")
        
    except Exception as e:
        logger.error(f"WebSocket auth failed: {e}")
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    await notification_manager.connect(websocket, user_id, user_role)
    
    try:
        with get_db_session() as db:
            unread_count = NotificationService.get_unread_count(db, user_id, user_role)
            await websocket.send_json({
                "type": "connected",
                "unread_count": unread_count
            })
        
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            elif data == "get_unread_count":
                with get_db_session() as db:
                    count = NotificationService.get_unread_count(db, user_id, user_role)
                    await websocket.send_json({"type": "unread_count", "count": count})
                
    except WebSocketDisconnect:
        notification_manager.disconnect(websocket, user_id, user_role)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        notification_manager.disconnect(websocket, user_id, user_role)

@router.get("/ws/stats")
def get_websocket_stats(current_user = Depends(get_current_user)):
    """Get WebSocket connection statistics (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return notification_manager.get_connection_count()
