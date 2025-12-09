"""
Push Notification Service using Firebase Cloud Messaging (FCM) HTTP v1 API
Sends push notifications to Android/iOS devices for all user roles
Notifications are sent in user's preferred language
"""
import os
import json
import httpx
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from models.user import User, UserRole, Language
from models.notification import NotificationType
from models.notification_settings import NotificationSettings
from services.notification_translations import get_notification_title, get_notification_message


class PushNotificationService:
    """Service to send push notifications via FCM"""
    
    FCM_API_URL = "https://fcm.googleapis.com/fcm/send"
    
    @staticmethod
    def get_fcm_server_key() -> Optional[str]:
        """Get FCM server key from environment"""
        return os.environ.get("FCM_SERVER_KEY")
    
    @staticmethod
    def get_notification_settings(db: Session) -> Optional[NotificationSettings]:
        """Get notification settings from database"""
        return db.query(NotificationSettings).first()
    
    @staticmethod
    def is_role_notifications_enabled(db: Session, role: UserRole) -> bool:
        """Check if notifications are enabled for a specific role"""
        settings = PushNotificationService.get_notification_settings(db)
        if not settings:
            return True
        
        if role == UserRole.CUSTOMER:
            return settings.customer_notifications_enabled
        elif role == UserRole.DRIVER:
            return settings.driver_notifications_enabled
        elif role == UserRole.ADMIN:
            return settings.admin_notifications_enabled
        return True
    
    @staticmethod
    def is_notification_type_enabled(db: Session, notification_type: NotificationType) -> bool:
        """Check if a specific notification type is enabled"""
        settings = PushNotificationService.get_notification_settings(db)
        if not settings:
            return True
        
        type_settings = {
            NotificationType.ORDER_INITIATED: settings.order_created_notify,
            NotificationType.NEW_ORDER: settings.order_created_notify,
            NotificationType.DRIVER_ASSIGNED: settings.order_assigned_notify,
            NotificationType.ORDER_ASSIGNED: settings.order_assigned_notify,
            NotificationType.ORDER_IN_TRANSIT: settings.delivery_started_notify,
            NotificationType.DELIVERY_STARTED: settings.delivery_started_notify,
            NotificationType.ORDER_DELIVERED: settings.delivery_completed_notify,
            NotificationType.DELIVERY_COMPLETED: settings.delivery_completed_notify,
            NotificationType.PAYMENT_RECEIVED: settings.payment_received_notify,
            NotificationType.PAYMENT_CONFIRMED: settings.payment_received_notify,
            NotificationType.LOW_STOCK: settings.low_stock_notify,
        }
        return type_settings.get(notification_type, True)
    
    @staticmethod
    def format_message(notification_type: NotificationType, metadata: Dict[str, Any], language: Language = Language.english) -> tuple:
        """Format notification title and message using templates in user's language"""
        title = get_notification_title(language, notification_type)
        message = get_notification_message(language, notification_type, metadata or {})
        return title, message
    
    @staticmethod
    def send_to_token(
        fcm_token: str,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send push notification to a single device token
        Returns True if successful, False otherwise
        """
        server_key = PushNotificationService.get_fcm_server_key()
        if not server_key:
            print("FCM_SERVER_KEY not configured. Skipping push notification.")
            return False
        
        if not fcm_token:
            return False
        
        headers = {
            "Authorization": f"key={server_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "to": fcm_token,
            "notification": {
                "title": title,
                "body": message,
                "sound": "default",
                "click_action": "OPEN_APP"
            },
            "data": data or {},
            "priority": "high"
        }
        
        try:
            response = httpx.post(
                PushNotificationService.FCM_API_URL,
                headers=headers,
                json=payload,
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success", 0) > 0:
                    print(f"Push notification sent successfully to token: {fcm_token[:20]}...")
                    return True
                else:
                    print(f"FCM returned failure: {result}")
                    return False
            else:
                print(f"FCM API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error sending push notification: {e}")
            return False
    
    @staticmethod
    def send_to_user(
        db: Session,
        user_id: int,
        notification_type: NotificationType,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send push notification to a specific user in their preferred language"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.fcm_token:
            return False
        
        if not PushNotificationService.is_role_notifications_enabled(db, user.role):
            print(f"Notifications disabled for role {user.role.value}")
            return False
        
        if not PushNotificationService.is_notification_type_enabled(db, notification_type):
            print(f"Notification type {notification_type.value} is disabled")
            return False
        
        user_language = user.base_language if user.base_language else Language.english
        
        title, message = PushNotificationService.format_message(
            notification_type, 
            metadata or {},
            user_language
        )
        
        data = {
            "type": notification_type.value,
            "click_action": "OPEN_APP",
            **(metadata or {})
        }
        
        for key, value in data.items():
            if not isinstance(value, str):
                data[key] = str(value)
        
        return PushNotificationService.send_to_token(
            user.fcm_token,
            title,
            message,
            data
        )
    
    @staticmethod
    def send_to_role(
        db: Session,
        role: UserRole,
        notification_type: NotificationType,
        metadata: Optional[Dict[str, Any]] = None,
        exclude_user_ids: Optional[List[int]] = None
    ) -> int:
        """
        Send push notification to all users of a specific role
        Each user receives notification in their preferred language
        Returns number of successful notifications sent
        """
        if not PushNotificationService.is_role_notifications_enabled(db, role):
            print(f"Notifications disabled for role {role.value}")
            return 0
        
        if not PushNotificationService.is_notification_type_enabled(db, notification_type):
            print(f"Notification type {notification_type.value} is disabled")
            return 0
        
        query = db.query(User).filter(
            User.role == role,
            User.fcm_token.isnot(None),
            User.fcm_token != ""
        )
        
        if exclude_user_ids:
            query = query.filter(~User.id.in_(exclude_user_ids))
        
        users = query.all()
        
        data = {
            "type": notification_type.value,
            "click_action": "OPEN_APP",
            **(metadata or {})
        }
        
        for key, value in data.items():
            if not isinstance(value, str):
                data[key] = str(value)
        
        success_count = 0
        for user in users:
            user_language = user.base_language if user.base_language else Language.english
            title, message = PushNotificationService.format_message(
                notification_type,
                metadata or {},
                user_language
            )
            if PushNotificationService.send_to_token(user.fcm_token, title, message, data):
                success_count += 1
        
        print(f"Sent push notification to {success_count}/{len(users)} {role.value}s")
        return success_count
    
    @staticmethod
    def notify_order_created(db: Session, order_id: int, customer_name: str, liters: float, amount: float):
        """Notify admins about new order"""
        metadata = {
            "order_id": order_id,
            "customer_name": customer_name,
            "liters": f"{liters:.1f}",
            "amount": f"{amount:,.2f}"
        }
        PushNotificationService.send_to_role(
            db, UserRole.ADMIN, NotificationType.NEW_ORDER, metadata
        )
    
    @staticmethod
    def notify_order_assigned(db: Session, order_id: int, driver_id: int, customer_id: int, 
                              driver_name: str, customer_name: str, liters: float):
        """Notify driver about assigned order and customer about driver assignment"""
        driver_metadata = {
            "order_id": order_id,
            "customer_name": customer_name,
            "liters": f"{liters:.1f}"
        }
        PushNotificationService.send_to_user(
            db, driver_id, NotificationType.ORDER_ASSIGNED, driver_metadata
        )
        
        customer_user = db.query(User).join(User.customer).filter(
            User.customer.has(id=customer_id)
        ).first()
        
        if customer_user:
            customer_metadata = {
                "order_id": order_id,
                "driver_name": driver_name
            }
            PushNotificationService.send_to_user(
                db, customer_user.id, NotificationType.DRIVER_ASSIGNED, customer_metadata
            )
    
    @staticmethod
    def notify_delivery_started(db: Session, order_id: int, customer_id: int, driver_name: str):
        """Notify customer and admins when delivery starts"""
        metadata = {
            "order_id": order_id,
            "driver_name": driver_name
        }
        
        customer_user = db.query(User).join(User.customer).filter(
            User.customer.has(id=customer_id)
        ).first()
        
        if customer_user:
            PushNotificationService.send_to_user(
                db, customer_user.id, NotificationType.ORDER_IN_TRANSIT, metadata
            )
        
        PushNotificationService.send_to_role(
            db, UserRole.ADMIN, NotificationType.DELIVERY_STARTED, metadata
        )
    
    @staticmethod
    def notify_delivery_completed(db: Session, order_id: int, customer_id: int, 
                                  driver_id: int, driver_name: str, liters: float):
        """Notify customer and admins when delivery is completed"""
        customer_metadata = {
            "order_id": order_id,
            "liters": f"{liters:.1f}",
            "driver_name": driver_name
        }
        
        customer_user = db.query(User).join(User.customer).filter(
            User.customer.has(id=customer_id)
        ).first()
        
        if customer_user:
            PushNotificationService.send_to_user(
                db, customer_user.id, NotificationType.ORDER_DELIVERED, customer_metadata
            )
        
        admin_metadata = {
            "order_id": order_id,
            "driver_name": driver_name
        }
        PushNotificationService.send_to_role(
            db, UserRole.ADMIN, NotificationType.DELIVERY_COMPLETED, admin_metadata
        )
    
    @staticmethod
    def notify_payment_received(db: Session, order_id: int, driver_id: int, amount: float):
        """Notify driver and admins about payment"""
        metadata = {
            "order_id": order_id,
            "amount": f"{amount:,.2f}"
        }
        
        PushNotificationService.send_to_user(
            db, driver_id, NotificationType.PAYMENT_CONFIRMED, metadata
        )
        
        PushNotificationService.send_to_role(
            db, UserRole.ADMIN, NotificationType.PAYMENT_RECEIVED, metadata
        )
    
    @staticmethod
    def notify_low_stock(db: Session, stock_level: float):
        """Notify admins about low stock"""
        metadata = {
            "stock_level": f"{stock_level:.1f}"
        }
        PushNotificationService.send_to_role(
            db, UserRole.ADMIN, NotificationType.LOW_STOCK, metadata
        )
