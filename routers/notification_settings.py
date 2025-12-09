from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models.notification_settings import NotificationSettings
from models.user import User
from utils.auth_dependency import get_current_admin

router = APIRouter(prefix="/api/notification-settings", tags=["Notification Settings"])


class NotificationSettingsResponse(BaseModel):
    id: int
    customer_notifications_enabled: bool
    driver_notifications_enabled: bool
    admin_notifications_enabled: bool
    sms_enabled: bool
    customer_sms_enabled: bool
    driver_sms_enabled: bool
    admin_sms_enabled: bool
    order_created_notify: bool
    order_assigned_notify: bool
    delivery_started_notify: bool
    delivery_completed_notify: bool
    payment_received_notify: bool
    low_stock_notify: bool
    
    class Config:
        from_attributes = True


class NotificationSettingsUpdate(BaseModel):
    customer_notifications_enabled: Optional[bool] = None
    driver_notifications_enabled: Optional[bool] = None
    admin_notifications_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    customer_sms_enabled: Optional[bool] = None
    driver_sms_enabled: Optional[bool] = None
    admin_sms_enabled: Optional[bool] = None
    order_created_notify: Optional[bool] = None
    order_assigned_notify: Optional[bool] = None
    delivery_started_notify: Optional[bool] = None
    delivery_completed_notify: Optional[bool] = None
    payment_received_notify: Optional[bool] = None
    low_stock_notify: Optional[bool] = None


def get_or_create_settings(db: Session) -> NotificationSettings:
    """Get existing settings or create default ones"""
    settings = db.query(NotificationSettings).first()
    if not settings:
        settings = NotificationSettings(
            customer_notifications_enabled=True,
            driver_notifications_enabled=True,
            admin_notifications_enabled=True,
            sms_enabled=True,
            customer_sms_enabled=True,
            driver_sms_enabled=True,
            admin_sms_enabled=True,
            order_created_notify=True,
            order_assigned_notify=True,
            delivery_started_notify=True,
            delivery_completed_notify=True,
            payment_received_notify=True,
            low_stock_notify=True
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/", response_model=NotificationSettingsResponse)
def get_notification_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get current notification settings (Admin only)"""
    settings = get_or_create_settings(db)
    return settings


@router.put("/", response_model=NotificationSettingsResponse)
def update_notification_settings(
    request: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update notification settings (Admin only)"""
    settings = get_or_create_settings(db)
    
    if request.customer_notifications_enabled is not None:
        settings.customer_notifications_enabled = request.customer_notifications_enabled
    if request.driver_notifications_enabled is not None:
        settings.driver_notifications_enabled = request.driver_notifications_enabled
    if request.admin_notifications_enabled is not None:
        settings.admin_notifications_enabled = request.admin_notifications_enabled
    if request.sms_enabled is not None:
        settings.sms_enabled = request.sms_enabled
    if request.customer_sms_enabled is not None:
        settings.customer_sms_enabled = request.customer_sms_enabled
    if request.driver_sms_enabled is not None:
        settings.driver_sms_enabled = request.driver_sms_enabled
    if request.admin_sms_enabled is not None:
        settings.admin_sms_enabled = request.admin_sms_enabled
    if request.order_created_notify is not None:
        settings.order_created_notify = request.order_created_notify
    if request.order_assigned_notify is not None:
        settings.order_assigned_notify = request.order_assigned_notify
    if request.delivery_started_notify is not None:
        settings.delivery_started_notify = request.delivery_started_notify
    if request.delivery_completed_notify is not None:
        settings.delivery_completed_notify = request.delivery_completed_notify
    if request.payment_received_notify is not None:
        settings.payment_received_notify = request.payment_received_notify
    if request.low_stock_notify is not None:
        settings.low_stock_notify = request.low_stock_notify
    
    db.commit()
    db.refresh(settings)
    
    return settings


@router.post("/toggle-role/{role}")
def toggle_role_notifications(
    role: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Toggle notifications for a specific role (Admin only)"""
    if role not in ["customer", "driver", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be customer, driver, or admin")
    
    settings = get_or_create_settings(db)
    
    if role == "customer":
        settings.customer_notifications_enabled = not settings.customer_notifications_enabled
        new_state = settings.customer_notifications_enabled
    elif role == "driver":
        settings.driver_notifications_enabled = not settings.driver_notifications_enabled
        new_state = settings.driver_notifications_enabled
    else:
        settings.admin_notifications_enabled = not settings.admin_notifications_enabled
        new_state = settings.admin_notifications_enabled
    
    db.commit()
    
    return {
        "message": f"Notifications for {role} {'enabled' if new_state else 'disabled'}",
        "role": role,
        "enabled": new_state
    }


@router.post("/toggle-all")
def toggle_all_notifications(
    enabled: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Enable or disable all notifications at once (Admin only)"""
    settings = get_or_create_settings(db)
    
    settings.customer_notifications_enabled = enabled
    settings.driver_notifications_enabled = enabled
    settings.admin_notifications_enabled = enabled
    settings.sms_enabled = enabled
    settings.customer_sms_enabled = enabled
    settings.driver_sms_enabled = enabled
    settings.admin_sms_enabled = enabled
    settings.order_created_notify = enabled
    settings.order_assigned_notify = enabled
    settings.delivery_started_notify = enabled
    settings.delivery_completed_notify = enabled
    settings.payment_received_notify = enabled
    settings.low_stock_notify = enabled
    
    db.commit()
    
    return {
        "message": f"All notifications {'enabled' if enabled else 'disabled'}",
        "enabled": enabled
    }


@router.post("/toggle-sms")
def toggle_sms_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Toggle SMS notifications globally (Admin only)"""
    settings = get_or_create_settings(db)
    
    settings.sms_enabled = not settings.sms_enabled
    new_state = settings.sms_enabled
    
    db.commit()
    
    return {
        "message": f"SMS notifications {'enabled' if new_state else 'disabled'}",
        "enabled": new_state
    }


@router.post("/toggle-sms-role/{role}")
def toggle_role_sms(
    role: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Toggle SMS for a specific role (Admin only)"""
    if role not in ["customer", "driver", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be customer, driver, or admin")
    
    settings = get_or_create_settings(db)
    
    if role == "customer":
        settings.customer_sms_enabled = not settings.customer_sms_enabled
        new_state = settings.customer_sms_enabled
    elif role == "driver":
        settings.driver_sms_enabled = not settings.driver_sms_enabled
        new_state = settings.driver_sms_enabled
    else:
        settings.admin_sms_enabled = not settings.admin_sms_enabled
        new_state = settings.admin_sms_enabled
    
    db.commit()
    
    return {
        "message": f"SMS for {role} {'enabled' if new_state else 'disabled'}",
        "role": role,
        "enabled": new_state
    }
