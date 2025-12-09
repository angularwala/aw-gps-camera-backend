from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal

from database import get_db
from models import Order, Transaction, Customer, User, VehicleOdometer
from models.order import OrderStatus
from models.user import UserRole
from utils.auth_dependency import get_current_user, get_current_admin

router = APIRouter(prefix="/api/reports", tags=["Reports"])

class ReportsSummaryResponse(BaseModel):
    total_orders: int = 0
    total_liters: float = 0.0
    total_revenue: float = 0.0
    pending_payments: float = 0.0
    total_customers: int = 0
    total_drivers: int = 0

@router.get("/summary", response_model=ReportsSummaryResponse)
def get_reports_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get overall reports summary"""
    total_orders = db.query(Order).count()
    
    total_liters = db.query(func.coalesce(func.sum(Order.liters), 0)).filter(
        Order.status == OrderStatus.DELIVERED
    ).scalar() or 0.0
    
    total_revenue = db.query(func.coalesce(func.sum(Order.amount), 0)).filter(
        Order.status == OrderStatus.DELIVERED
    ).scalar() or 0.0
    
    total_order_amount = db.query(func.coalesce(func.sum(Order.amount), 0)).scalar() or 0.0
    total_paid = db.query(func.coalesce(func.sum(Transaction.paid), 0)).filter(
        Transaction.is_payment == True
    ).scalar() or 0.0
    pending_payments = float(total_order_amount) - float(total_paid)
    if pending_payments < 0:
        pending_payments = 0.0
    
    total_customers = db.query(Customer).count()
    total_drivers = db.query(User).filter(User.role == UserRole.DRIVER).count()
    
    return ReportsSummaryResponse(
        total_orders=total_orders,
        total_liters=float(total_liters),
        total_revenue=float(total_revenue),
        pending_payments=pending_payments,
        total_customers=total_customers,
        total_drivers=total_drivers
    )

class CustomerReportItem(BaseModel):
    customer_id: int
    customer_name: str
    total_orders: int
    total_liters: float
    total_amount: float
    pending_amount: float
    last_order_date: Optional[datetime]
    
    class Config:
        from_attributes = True

class VehicleKmReport(BaseModel):
    driver_id: int
    driver_name: str
    date: date
    total_km: float
    fuel_consumed: Optional[float]
    
    class Config:
        from_attributes = True

class AccountStatementItem(BaseModel):
    id: int
    date: datetime
    type: str
    description: str
    order_id: Optional[int]
    debit: float
    credit: float
    balance: float
    
    class Config:
        from_attributes = True

class SalesReportItem(BaseModel):
    date: date
    total_orders: int
    total_liters: float
    total_amount: float
    pending_amount: float
    completed_orders: int
    
    class Config:
        from_attributes = True

class DriverDeliveryReportItem(BaseModel):
    date: date
    total_deliveries: int
    completed_deliveries: int
    cancelled_deliveries: int
    total_liters: float
    total_amount: float
    customers_served: int
    
    class Config:
        from_attributes = True

class DriverDeliveryReportSummary(BaseModel):
    period: str
    start_date: date
    end_date: date
    total_deliveries: int
    completed_deliveries: int
    cancelled_deliveries: int
    total_liters: float
    total_amount: float
    customers_served: int
    daily_breakdown: List[DriverDeliveryReportItem]
    
    class Config:
        from_attributes = True

@router.get("/driver-deliveries", response_model=DriverDeliveryReportSummary)
def get_driver_delivery_report(
    period: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get delivery report for the logged-in driver (daily/weekly/monthly)
    
    Uses updated_at for delivered/cancelled orders (completion time) and 
    created_at for pending/in-progress orders.
    """
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=403, detail="Only drivers can access this report")
    
    # Calculate date range based on period
    today = date.today()
    if period == "daily":
        start_date = today
        end_date = today
    elif period == "weekly":
        # Start from Monday of current week
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    else:  # monthly
        start_date = today.replace(day=1)
        end_date = today
    
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Query completed/cancelled orders by their completion time (updated_at)
    completed_orders = db.query(Order).filter(
        and_(
            Order.driver_id == current_user.id,
            Order.status.in_([OrderStatus.DELIVERED, OrderStatus.CANCELLED]),
            Order.updated_at >= start_datetime,
            Order.updated_at <= end_datetime
        )
    ).all()
    
    # Query in-progress orders by their assignment time (created_at or updated_at)
    pending_orders = db.query(Order).filter(
        and_(
            Order.driver_id == current_user.id,
            Order.status.in_([OrderStatus.ASSIGNED, OrderStatus.IN_TRANSIT]),
            Order.updated_at >= start_datetime,
            Order.updated_at <= end_datetime
        )
    ).all()
    
    # Combine all orders
    all_orders = completed_orders + pending_orders
    
    # Calculate totals
    total_deliveries = len(all_orders)
    completed_deliveries = len([o for o in all_orders if o.status == OrderStatus.DELIVERED])
    cancelled_deliveries = len([o for o in all_orders if o.status == OrderStatus.CANCELLED])
    total_liters = sum(float(o.liters or 0) for o in all_orders if o.status == OrderStatus.DELIVERED)
    total_amount = sum(float(o.amount or 0) for o in all_orders if o.status == OrderStatus.DELIVERED)
    customers_served = len(set(o.customer_id for o in all_orders if o.status == OrderStatus.DELIVERED))
    
    # Group by date for daily breakdown (use updated_at for completed, created_at for pending)
    daily_data = {}
    for order in all_orders:
        # Use updated_at as the activity date
        order_date = order.updated_at.date()
        if order_date not in daily_data:
            daily_data[order_date] = {
                'total': 0,
                'completed': 0,
                'cancelled': 0,
                'liters': 0.0,
                'amount': 0.0,
                'customers': set()
            }
        
        daily_data[order_date]['total'] += 1
        if order.status == OrderStatus.DELIVERED:
            daily_data[order_date]['completed'] += 1
            daily_data[order_date]['liters'] += float(order.liters or 0)
            daily_data[order_date]['amount'] += float(order.amount or 0)
            daily_data[order_date]['customers'].add(order.customer_id)
        elif order.status == OrderStatus.CANCELLED:
            daily_data[order_date]['cancelled'] += 1
    
    # Sort chronologically (oldest first)
    daily_breakdown = [
        DriverDeliveryReportItem(
            date=d,
            total_deliveries=data['total'],
            completed_deliveries=data['completed'],
            cancelled_deliveries=data['cancelled'],
            total_liters=data['liters'],
            total_amount=data['amount'],
            customers_served=len(data['customers'])
        )
        for d, data in sorted(daily_data.items(), reverse=True)
    ]
    
    return DriverDeliveryReportSummary(
        period=period,
        start_date=start_date,
        end_date=end_date,
        total_deliveries=total_deliveries,
        completed_deliveries=completed_deliveries,
        cancelled_deliveries=cancelled_deliveries,
        total_liters=total_liters,
        total_amount=total_amount,
        customers_served=customers_served,
        daily_breakdown=daily_breakdown
    )

@router.get("/customer-summary", response_model=List[CustomerReportItem])
def get_customer_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get comprehensive customer report with order summary"""
    # First get customer orders summary
    query = db.query(
        Customer.id.label('customer_id'),
        Customer.company_name.label('customer_name'),
        func.count(Order.id).label('total_orders'),
        func.sum(Order.liters).label('total_liters'),
        func.sum(Order.amount).label('total_amount'),
        func.max(Order.created_at).label('last_order_date')
    ).join(Order, Customer.id == Order.customer_id, isouter=True)
    
    if start_date:
        query = query.filter(Order.created_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(Order.created_at <= datetime.combine(end_date, datetime.max.time()))
    
    results = query.group_by(Customer.id, Customer.company_name).all()
    
    # Calculate pending amounts from transactions
    report_items = []
    for r in results:
        pending = db.query(func.sum(Transaction.due)).filter(
            Transaction.customer_id == r.customer_id
        ).scalar() or 0
        
        report_items.append(CustomerReportItem(
            customer_id=r.customer_id,
            customer_name=r.customer_name,
            total_orders=r.total_orders or 0,
            total_liters=float(r.total_liters or 0),
            total_amount=float(r.total_amount or 0),
            pending_amount=float(pending),
            last_order_date=r.last_order_date
        ))
    
    return report_items

@router.get("/sales-summary", response_model=List[SalesReportItem])
def get_sales_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get sales summary grouped by period (daily/weekly/monthly)"""
    if not start_date:
        start_date = date.today() - timedelta(days=30)
    if not end_date:
        end_date = date.today()
    
    if period == "daily":
        date_trunc = func.date(Order.created_at)
    elif period == "weekly":
        date_trunc = func.date_trunc('week', Order.created_at)
    else:  # monthly
        date_trunc = func.date_trunc('month', Order.created_at)
    
    results = db.query(
        date_trunc.label('date'),
        func.count(Order.id).label('total_orders'),
        func.sum(Order.liters).label('total_liters'),
        func.sum(Order.amount).label('total_amount'),
        func.count(func.nullif(Order.status == OrderStatus.DELIVERED, False)).label('completed_orders')
    ).filter(
        and_(
            Order.created_at >= datetime.combine(start_date, datetime.min.time()),
            Order.created_at <= datetime.combine(end_date, datetime.max.time())
        )
    ).group_by(date_trunc).order_by(date_trunc.desc()).all()
    
    # Calculate pending amounts from transactions for each period
    report_items = []
    for r in results:
        # Get pending amount for orders in this period
        period_start = r.date if isinstance(r.date, datetime) else datetime.combine(r.date, datetime.min.time())
        if period == "weekly":
            period_end = period_start + timedelta(days=7)
        elif period == "monthly":
            # Add one month
            if period_start.month == 12:
                period_end = period_start.replace(year=period_start.year + 1, month=1)
            else:
                period_end = period_start.replace(month=period_start.month + 1)
        else:  # daily
            period_end = period_start + timedelta(days=1)
        
        # Get order IDs for this period
        order_ids = db.query(Order.id).filter(
            and_(
                Order.created_at >= period_start,
                Order.created_at < period_end
            )
        ).all()
        order_ids = [oid[0] for oid in order_ids]
        
        # Sum pending amounts from transactions for these orders
        pending = 0
        if order_ids:
            pending = db.query(func.sum(Transaction.due)).filter(
                Transaction.order_id.in_(order_ids)
            ).scalar() or 0
        
        report_items.append(SalesReportItem(
            date=r.date.date() if isinstance(r.date, datetime) else r.date,
            total_orders=r.total_orders or 0,
            total_liters=float(r.total_liters or 0),
            total_amount=float(r.total_amount or 0),
            pending_amount=float(pending),
            completed_orders=r.completed_orders or 0
        ))
    
    return report_items

@router.get("/vehicle-km", response_model=List[VehicleKmReport])
def get_vehicle_km_report(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    driver_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get vehicle kilometer tracking report"""
    if not start_date:
        start_date = date.today() - timedelta(days=30)
    if not end_date:
        end_date = date.today()
    
    query = db.query(VehicleOdometer, User.name).join(
        User, VehicleOdometer.driver_id == User.id
    ).filter(
        and_(
            VehicleOdometer.date >= start_date,
            VehicleOdometer.date <= end_date
        )
    )
    
    if driver_id:
        query = query.filter(VehicleOdometer.driver_id == driver_id)
    
    results = query.order_by(VehicleOdometer.date.desc()).all()
    
    return [VehicleKmReport(
        driver_id=record.driver_id,
        driver_name=name,
        date=record.date,
        total_km=record.total_km,
        fuel_consumed=record.fuel_consumed
    ) for record, name in results]

@router.get("/account-statement/{customer_id}", response_model=List[AccountStatementItem])
def get_account_statement(
    customer_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed account statement for a customer"""
    # Verify access
    if current_user.role == UserRole.CUSTOMER:
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        if not customer or customer.id != customer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not start_date:
        start_date = date.today() - timedelta(days=90)
    if not end_date:
        end_date = date.today()
    
    # Get all transactions
    transactions = db.query(Transaction).filter(
        and_(
            Transaction.customer_id == customer_id,
            Transaction.date >= datetime.combine(start_date, datetime.min.time()),
            Transaction.date <= datetime.combine(end_date, datetime.max.time())
        )
    ).order_by(Transaction.date.asc()).all()
    
    # Calculate running balance
    balance = 0.0
    statement = []
    
    for txn in transactions:
        if not txn.is_payment:
            # Order (debit)
            balance += float(txn.amount)
            statement.append(AccountStatementItem(
                id=txn.id,
                date=txn.date,
                type='Order',
                description=f'Order #{txn.order_id}' if txn.order_id else 'Order',
                order_id=txn.order_id,
                debit=float(txn.amount),
                credit=0.0,
                balance=balance
            ))
        else:
            # Payment (credit)
            balance -= float(txn.paid or txn.amount)
            statement.append(AccountStatementItem(
                id=txn.id,
                date=txn.date,
                type='Payment',
                description='Payment received',
                order_id=txn.order_id,
                debit=0.0,
                credit=float(txn.paid or txn.amount),
                balance=balance
            ))
    
    return statement

class VehicleKmEntryRequest(BaseModel):
    driver_id: Optional[int] = None
    date: date
    start_km: float
    end_km: float
    fuel_consumed: Optional[float] = None
    notes: Optional[str] = None

@router.post("/vehicle-km")
def add_vehicle_km_entry(
    entry_data: VehicleKmEntryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add daily vehicle kilometer entry (Driver or Admin)"""
    if current_user.role not in [UserRole.DRIVER, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only drivers and admins can add vehicle tracking")
    
    # Determine the actual driver_id
    if current_user.role == UserRole.DRIVER:
        # Drivers can only submit for themselves
        driver_id = current_user.id
        if entry_data.driver_id and entry_data.driver_id != current_user.id:
            raise HTTPException(status_code=403, detail="Drivers can only submit entries for themselves")
    else:  # Admin
        # Admins must specify a driver_id
        if not entry_data.driver_id:
            raise HTTPException(status_code=400, detail="Admin must specify driver_id")
        driver_id = entry_data.driver_id
        
        # Verify the driver exists and is actually a driver
        driver = db.query(User).filter(User.id == driver_id).first()
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        if driver.role != UserRole.DRIVER:
            raise HTTPException(status_code=400, detail="Specified user is not a driver")
    
    # Check for duplicate entry
    existing = db.query(VehicleOdometer).filter(
        and_(
            VehicleOdometer.driver_id == driver_id,
            VehicleOdometer.date == entry_data.date
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Entry already exists for this date")
    
    if entry_data.end_km < entry_data.start_km:
        raise HTTPException(status_code=400, detail="End KM must be greater than start KM")
    
    total_km = entry_data.end_km - entry_data.start_km
    
    entry = VehicleOdometer(
        driver_id=driver_id,
        date=entry_data.date,
        start_km=entry_data.start_km,
        end_km=entry_data.end_km,
        total_km=total_km,
        fuel_consumed=entry_data.fuel_consumed,
        notes=entry_data.notes
    )
    
    db.add(entry)
    db.commit()
    db.refresh(entry)
    
    return {"message": "Vehicle KM entry added successfully", "entry_id": entry.id, "driver_id": driver_id}
