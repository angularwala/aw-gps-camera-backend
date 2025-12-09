"""
SMS Notification Service using Twilio
Sends SMS notifications to users for order updates and alerts
SMS messages are sent in user's preferred language
"""
import os
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from models.user import User, UserRole, Language
from models.notification import NotificationType
from models.notification_settings import NotificationSettings
from services.notification_translations import get_sms_message

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    Client = None


class SMSService:
    """Service to send SMS notifications via Twilio"""
    
    @staticmethod
    def get_twilio_credentials() -> tuple:
        """Get Twilio credentials from environment"""
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        from_number = os.environ.get("TWILIO_PHONE_NUMBER")
        return account_sid, auth_token, from_number
    
    @staticmethod
    def is_configured() -> bool:
        """Check if Twilio is properly configured"""
        if not TWILIO_AVAILABLE:
            return False
        account_sid, auth_token, from_number = SMSService.get_twilio_credentials()
        return all([account_sid, auth_token, from_number])
    
    @staticmethod
    def get_notification_settings(db: Session) -> Optional[NotificationSettings]:
        """Get notification settings from database"""
        return db.query(NotificationSettings).first()
    
    @staticmethod
    def is_sms_enabled(db: Session) -> bool:
        """Check if SMS is globally enabled"""
        settings = SMSService.get_notification_settings(db)
        if not settings:
            return True
        return settings.sms_enabled
    
    @staticmethod
    def is_role_sms_enabled(db: Session, role: UserRole) -> bool:
        """Check if SMS is enabled for a specific role"""
        settings = SMSService.get_notification_settings(db)
        if not settings:
            return True
        
        if not settings.sms_enabled:
            return False
        
        if role == UserRole.CUSTOMER:
            return settings.customer_sms_enabled
        elif role == UserRole.DRIVER:
            return settings.driver_sms_enabled
        elif role == UserRole.ADMIN:
            return settings.admin_sms_enabled
        return True
    
    @staticmethod
    def is_notification_type_enabled(db: Session, notification_type: NotificationType) -> bool:
        """Check if a specific notification type is enabled"""
        settings = SMSService.get_notification_settings(db)
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
    def format_message(notification_type: NotificationType, metadata: Dict[str, Any], language: Language = Language.english) -> str:
        """Format SMS message using templates in user's language"""
        return get_sms_message(language, notification_type, metadata or {})
    
    @staticmethod
    def send_sms(to_number: str, message: str) -> bool:
        """
        Send SMS to a phone number
        Returns True if successful, False otherwise
        """
        if not SMSService.is_configured():
            print("Twilio not configured. Skipping SMS.")
            return False
        
        account_sid, auth_token, from_number = SMSService.get_twilio_credentials()
        
        if not to_number or len(to_number) < 10:
            print(f"Invalid phone number: {to_number}")
            return False
        
        formatted_number = to_number
        if not to_number.startswith('+'):
            formatted_number = f"+91{to_number}"
        
        try:
            client = Client(account_sid, auth_token)
            
            sms = client.messages.create(
                body=message,
                from_=from_number,
                to=formatted_number
            )
            
            print(f"SMS sent successfully. SID: {sms.sid}")
            return True
            
        except Exception as e:
            print(f"Error sending SMS: {e}")
            return False
    
    @staticmethod
    def send_to_user(
        db: Session,
        user_id: int,
        notification_type: NotificationType,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send SMS notification to a specific user in their preferred language"""
        if not SMSService.is_sms_enabled(db):
            print("SMS notifications are disabled globally")
            return False
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.mobile:
            return False
        
        if not SMSService.is_role_sms_enabled(db, user.role):
            print(f"SMS disabled for role {user.role.value}")
            return False
        
        if not SMSService.is_notification_type_enabled(db, notification_type):
            print(f"Notification type {notification_type.value} is disabled")
            return False
        
        user_language = user.base_language if user.base_language else Language.english
        message = SMSService.format_message(notification_type, metadata or {}, user_language)
        
        return SMSService.send_sms(user.mobile, message)
    
    @staticmethod
    def send_to_role(
        db: Session,
        role: UserRole,
        notification_type: NotificationType,
        metadata: Optional[Dict[str, Any]] = None,
        exclude_user_ids: Optional[list] = None
    ) -> int:
        """
        Send SMS to all users of a specific role
        Each user receives SMS in their preferred language
        Returns number of successful SMS sent
        """
        if not SMSService.is_sms_enabled(db):
            print("SMS notifications are disabled globally")
            return 0
        
        if not SMSService.is_role_sms_enabled(db, role):
            print(f"SMS disabled for role {role.value}")
            return 0
        
        if not SMSService.is_notification_type_enabled(db, notification_type):
            print(f"Notification type {notification_type.value} is disabled")
            return 0
        
        query = db.query(User).filter(
            User.role == role,
            User.mobile.isnot(None),
            User.mobile != ""
        )
        
        if exclude_user_ids:
            query = query.filter(~User.id.in_(exclude_user_ids))
        
        users = query.all()
        
        success_count = 0
        for user in users:
            user_language = user.base_language if user.base_language else Language.english
            message = SMSService.format_message(notification_type, metadata or {}, user_language)
            if SMSService.send_sms(user.mobile, message):
                success_count += 1
        
        print(f"Sent SMS to {success_count}/{len(users)} {role.value}s")
        return success_count
    
    @staticmethod
    def notify_order_created(db: Session, order_id: int, customer_name: str, liters: float, amount: float):
        """Notify admins about new order via SMS"""
        metadata = {
            "order_id": order_id,
            "customer_name": customer_name,
            "liters": f"{liters:.1f}",
            "amount": f"{amount:,.2f}"
        }
        SMSService.send_to_role(db, UserRole.ADMIN, NotificationType.NEW_ORDER, metadata)
    
    @staticmethod
    def notify_order_assigned(db: Session, order_id: int, driver_id: int, customer_id: int,
                              driver_name: str, customer_name: str, liters: float):
        """Notify driver and customer about order assignment via SMS"""
        driver_metadata = {
            "order_id": order_id,
            "customer_name": customer_name,
            "liters": f"{liters:.1f}"
        }
        SMSService.send_to_user(db, driver_id, NotificationType.ORDER_ASSIGNED, driver_metadata)
        
        from models.customer import Customer
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if customer and customer.user_id:
            customer_metadata = {
                "order_id": order_id,
                "driver_name": driver_name
            }
            SMSService.send_to_user(db, customer.user_id, NotificationType.DRIVER_ASSIGNED, customer_metadata)
    
    @staticmethod
    def notify_delivery_started(db: Session, order_id: int, customer_id: int, driver_name: str):
        """Notify customer when delivery starts via SMS"""
        from models.customer import Customer
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        
        if customer and customer.user_id:
            metadata = {
                "order_id": order_id,
                "driver_name": driver_name
            }
            SMSService.send_to_user(db, customer.user_id, NotificationType.ORDER_IN_TRANSIT, metadata)
    
    @staticmethod
    def notify_delivery_completed(db: Session, order_id: int, customer_id: int,
                                  driver_id: int, driver_name: str, liters: float):
        """Notify customer when delivery is completed via SMS"""
        from models.customer import Customer
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        
        if customer and customer.user_id:
            metadata = {
                "order_id": order_id,
                "liters": f"{liters:.1f}",
                "driver_name": driver_name
            }
            SMSService.send_to_user(db, customer.user_id, NotificationType.ORDER_DELIVERED, metadata)
    
    @staticmethod
    def notify_payment_received(db: Session, order_id: int, driver_id: int, amount: float):
        """Notify driver about payment via SMS"""
        metadata = {
            "order_id": order_id,
            "amount": f"{amount:,.2f}"
        }
        SMSService.send_to_user(db, driver_id, NotificationType.PAYMENT_CONFIRMED, metadata)
