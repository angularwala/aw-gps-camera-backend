from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models.user import User, UserRole
from models.customer import Customer
from models.order import Order, OrderStatus
from models.transaction import Transaction
from utils.auth_dependency import get_current_admin
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

class DashboardStatsResponse(BaseModel):
    total_customers: int = 0
    active_customers: int = 0
    total_drivers: int = 0
    active_drivers: int = 0
    total_orders: int = 0
    pending_orders: int = 0
    completed_orders: int = 0
    today_orders: int = 0
    total_revenue: float = 0.0
    today_revenue: float = 0.0
    pending_payments: float = 0.0
    total_liters_delivered: float = 0.0

@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get dashboard statistics for admin"""
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    
    total_customers = db.query(Customer).count()
    active_customers = db.query(Customer).filter(Customer.is_active == True).count()
    
    total_drivers = db.query(User).filter(User.role == UserRole.DRIVER).count()
    active_drivers = db.query(User).filter(
        User.role == UserRole.DRIVER,
        User.is_active == True
    ).count()
    
    total_orders = db.query(Order).count()
    pending_orders = db.query(Order).filter(
        Order.status.in_([OrderStatus.PENDING, OrderStatus.ASSIGNED, OrderStatus.IN_TRANSIT])
    ).count()
    completed_orders = db.query(Order).filter(Order.status == OrderStatus.DELIVERED).count()
    today_orders = db.query(Order).filter(Order.created_at >= today_start).count()
    
    total_revenue = db.query(func.coalesce(func.sum(Transaction.paid), 0)).filter(
        Transaction.is_payment == True
    ).scalar() or 0.0
    
    today_revenue = db.query(func.coalesce(func.sum(Transaction.paid), 0)).filter(
        Transaction.is_payment == True,
        Transaction.date >= today_start
    ).scalar() or 0.0
    
    total_order_amount = db.query(func.coalesce(func.sum(Order.amount), 0)).scalar() or 0.0
    pending_payments = float(total_order_amount) - float(total_revenue)
    if pending_payments < 0:
        pending_payments = 0.0
    
    total_liters = db.query(func.coalesce(func.sum(Order.liters), 0)).filter(
        Order.status == OrderStatus.DELIVERED
    ).scalar() or 0.0
    
    return DashboardStatsResponse(
        total_customers=total_customers,
        active_customers=active_customers,
        total_drivers=total_drivers,
        active_drivers=active_drivers,
        total_orders=total_orders,
        pending_orders=pending_orders,
        completed_orders=completed_orders,
        today_orders=today_orders,
        total_revenue=float(total_revenue),
        today_revenue=float(today_revenue),
        pending_payments=pending_payments,
        total_liters_delivered=float(total_liters)
    )
