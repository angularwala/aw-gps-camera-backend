from sqlalchemy.orm import Session
from models import Notification, NotificationType, UserRole, User
from models.user import Language
from typing import Optional, Dict, Any
import asyncio
import logging
from services.notification_translations import NOTIFICATION_TITLES, NOTIFICATION_MESSAGES

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for creating and managing notifications"""
    
    @staticmethod
    def get_user_language(db: Session, user_id: Optional[int]) -> Language:
        """Get user's preferred language, defaults to English"""
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.base_language:
                return user.base_language
        return Language.english
    
    @staticmethod
    def get_translated_content(
        notification_type: NotificationType,
        language: Language,
        metadata: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """Get translated title and message for a notification"""
        # Get title for user's language, fallback to English
        titles = NOTIFICATION_TITLES.get(language, NOTIFICATION_TITLES.get(Language.english, {}))
        title = titles.get(notification_type, f"Notification: {notification_type.value}")
        
        # Get message for user's language, fallback to English
        messages = NOTIFICATION_MESSAGES.get(language, NOTIFICATION_MESSAGES.get(Language.english, {}))
        message_template = messages.get(notification_type, "")
        
        # Format message with metadata
        formatted_message = message_template
        if metadata and message_template:
            try:
                formatted_message = message_template.format(**metadata)
            except KeyError:
                # Missing key in metadata, use template as-is
                pass
        
        return title, formatted_message
    
    @staticmethod
    def create_notification(
        db: Session,
        role: UserRole,
        notification_type: NotificationType,
        user_id: Optional[int] = None,
        order_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Notification:
        """
        Create a new notification in user's preferred language
        
        Args:
            db: Database session
            role: Target user role (admin, driver, customer)
            notification_type: Type of notification
            user_id: Specific user ID (None for broadcast to all users of the role)
            order_id: Related order ID
            metadata: Additional data for template interpolation
        
        Returns:
            Created notification object
        """
        # Get user's language preference
        language = NotificationService.get_user_language(db, user_id)
        
        # Get translated title and message
        title, formatted_message = NotificationService.get_translated_content(
            notification_type, language, metadata
        )
        
        notification = Notification(
            user_id=user_id,
            role=role,
            order_id=order_id,
            type=notification_type,
            title=title,
            message=formatted_message,
            extra_data=metadata,
            is_read=False
        )
        
        db.add(notification)
        db.commit()
        db.refresh(notification)
        
        try:
            from services.notification_broadcast import broadcast_new_notification
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(broadcast_new_notification(
                    notification_id=notification.id,
                    notification_type=notification_type.value if hasattr(notification_type, 'value') else str(notification_type),
                    title=title,
                    message=formatted_message,
                    user_id=user_id,
                    role=role.value if hasattr(role, 'value') else str(role),
                    order_id=order_id,
                    extra_data=metadata
                ))
            else:
                loop.run_until_complete(broadcast_new_notification(
                    notification_id=notification.id,
                    notification_type=notification_type.value if hasattr(notification_type, 'value') else str(notification_type),
                    title=title,
                    message=formatted_message,
                    user_id=user_id,
                    role=role.value if hasattr(role, 'value') else str(role),
                    order_id=order_id,
                    extra_data=metadata
                ))
        except Exception as e:
            logger.warning(f"Failed to broadcast notification: {e}")
        
        return notification
    
    @staticmethod
    def mark_as_read(db: Session, notification_id: int, user_id: int, user_role: str) -> bool:
        """Mark a notification as read - handles both user-specific and role-broadcast notifications"""
        from sqlalchemy import or_
        
        # Find notification that belongs to this user (either user-specific OR role-broadcast)
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            or_(
                Notification.user_id == user_id,
                (Notification.user_id == None) & (Notification.role == user_role)
            )
        ).first()
        
        if notification:
            # For broadcast notifications, we can't just mark them as read globally
            # since they're shared across all users of that role
            # Instead, we would need a separate read-tracking table
            # For now, we'll allow marking broadcast notifications as read
            notification.is_read = True
            db.commit()
            return True
        return False
    
    @staticmethod
    def mark_all_as_read(db: Session, user_id: int, user_role: str) -> int:
        """Mark all notifications for a user as read (user-specific only, not broadcast)"""
        from sqlalchemy import or_
        
        # NOTE: Only mark user-specific notifications as read
        # Broadcast notifications (user_id=NULL) are shared across all users of that role
        # Marking them read would affect all users, which is incorrect behavior
        # In the future, implement a separate notification_reads table to track per-user read status
        count = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({"is_read": True})
        db.commit()
        return count
    
    @staticmethod
    def get_user_notifications(
        db: Session, 
        user_id: int,
        user_role: str,
        unread_only: bool = False,
        limit: int = 50
    ) -> list[Notification]:
        """Get notifications for a specific user - includes user-specific AND role-broadcast notifications"""
        from sqlalchemy import or_
        
        # Get notifications that are either:
        # 1. Specifically for this user (user_id matches)
        # 2. Broadcast to this user's role (user_id is NULL and role matches)
        query = db.query(Notification).filter(
            or_(
                Notification.user_id == user_id,
                (Notification.user_id == None) & (Notification.role == user_role)
            )
        )
        
        if unread_only:
            query = query.filter(Notification.is_read == False)
        
        return query.order_by(Notification.created_at.desc()).limit(limit).all()
    
    @staticmethod
    def get_unread_count(db: Session, user_id: int, user_role: str) -> int:
        """Get count of unread notifications for a user"""
        from sqlalchemy import or_
        
        return db.query(Notification).filter(
            or_(
                Notification.user_id == user_id,
                (Notification.user_id == None) & (Notification.role == user_role)
            ),
            Notification.is_read == False
        ).count()
