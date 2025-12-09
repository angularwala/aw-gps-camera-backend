from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from database import Base


class NotificationSettings(Base):
    __tablename__ = "notification_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    customer_notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    driver_notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    admin_notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    
    sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    customer_sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    driver_sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    admin_sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    
    order_created_notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    order_assigned_notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    delivery_started_notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    delivery_completed_notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    payment_received_notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    low_stock_notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
