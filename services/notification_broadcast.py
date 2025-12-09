from fastapi import WebSocket
from typing import Dict, List, Optional
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

class NotificationConnectionManager:
    """Manages WebSocket connections for real-time notification broadcasting"""
    
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.role_connections: Dict[str, List[WebSocket]] = {
            "admin": [],
            "driver": [],
            "customer": []
        }
    
    async def connect(self, websocket: WebSocket, user_id: int, role: str):
        """Accept a WebSocket connection and track it by user_id and role"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        
        if role in self.role_connections:
            self.role_connections[role].append(websocket)
        
        logger.info(f"WebSocket connected: user_id={user_id}, role={role}")
    
    def disconnect(self, websocket: WebSocket, user_id: int, role: str):
        """Remove a WebSocket connection"""
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
            except ValueError:
                pass
        
        if role in self.role_connections:
            try:
                self.role_connections[role].remove(websocket)
            except ValueError:
                pass
        
        logger.info(f"WebSocket disconnected: user_id={user_id}, role={role}")
    
    async def send_to_user(self, user_id: int, message: dict):
        """Send notification to a specific user"""
        if user_id in self.active_connections:
            disconnected = []
            for websocket in self.active_connections[user_id]:
                try:
                    await websocket.send_json(message)
                    logger.info(f"Notification sent to user_id={user_id}")
                except Exception as e:
                    logger.error(f"Failed to send to user_id={user_id}: {e}")
                    disconnected.append(websocket)
            
            for ws in disconnected:
                try:
                    self.active_connections[user_id].remove(ws)
                except:
                    pass
    
    async def broadcast_to_role(self, role: str, message: dict):
        """Broadcast notification to all users of a specific role"""
        if role not in self.role_connections:
            return
        
        disconnected = []
        for websocket in self.role_connections[role]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to broadcast to role={role}: {e}")
                disconnected.append(websocket)
        
        for ws in disconnected:
            try:
                self.role_connections[role].remove(ws)
            except:
                pass
        
        logger.info(f"Broadcast sent to role={role}, recipients={len(self.role_connections[role])}")
    
    async def broadcast_notification(
        self, 
        notification_id: int,
        notification_type: str,
        title: str,
        message: str,
        user_id: Optional[int] = None,
        role: Optional[str] = None,
        order_id: Optional[int] = None,
        extra_data: Optional[dict] = None
    ):
        """Broadcast a notification to the appropriate recipients"""
        payload = {
            "type": "new_notification",
            "notification": {
                "id": notification_id,
                "notification_type": notification_type,
                "title": title,
                "message": message,
                "order_id": order_id,
                "extra_data": extra_data,
                "is_read": False
            }
        }
        
        if user_id:
            await self.send_to_user(user_id, payload)
        elif role:
            await self.broadcast_to_role(role, payload)
    
    def get_connection_count(self) -> dict:
        """Get current connection statistics"""
        return {
            "total_users": len(self.active_connections),
            "by_role": {
                role: len(connections) 
                for role, connections in self.role_connections.items()
            }
        }

notification_manager = NotificationConnectionManager()

async def broadcast_new_notification(
    notification_id: int,
    notification_type: str,
    title: str,
    message: str,
    user_id: Optional[int] = None,
    role: Optional[str] = None,
    order_id: Optional[int] = None,
    extra_data: Optional[dict] = None
):
    """Helper function to broadcast a notification"""
    await notification_manager.broadcast_notification(
        notification_id=notification_id,
        notification_type=notification_type,
        title=title,
        message=message,
        user_id=user_id,
        role=role,
        order_id=order_id,
        extra_data=extra_data
    )
