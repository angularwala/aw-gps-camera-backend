from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date, timedelta
from decimal import Decimal
from database import get_db
from models.stock import StockTransaction, StockTransactionType, CurrentStock
from models.order import Order, OrderStatus
from models.user import User
from utils.auth_dependency import get_current_admin, get_current_user

router = APIRouter(prefix="/api/stock", tags=["Stock Management"])


class StockTransactionCreate(BaseModel):
    transaction_type: str
    liters: float
    rate_per_liter: Optional[float] = None
    total_amount: Optional[float] = None
    supplier_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    invoice_number: Optional[str] = None
    notes: Optional[str] = None
    transaction_date: Optional[datetime] = None


class StockTransactionResponse(BaseModel):
    id: int
    transaction_type: str
    liters: float
    rate_per_liter: Optional[float]
    total_amount: Optional[float]
    supplier_name: Optional[str]
    vehicle_number: Optional[str]
    invoice_number: Optional[str]
    order_id: Optional[int]
    notes: Optional[str]
    recorded_by: int
    recorded_by_name: Optional[str] = None
    transaction_date: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


class CurrentStockResponse(BaseModel):
    total_liters: float
    last_updated: datetime
    
    class Config:
        from_attributes = True


class StockSummary(BaseModel):
    current_stock: float
    total_stock_in: float
    total_stock_out: float
    total_purchase_amount: float
    total_sales_amount: float
    last_updated: datetime


class StockReportItem(BaseModel):
    date: date
    stock_in: float
    stock_out: float
    opening_balance: float
    closing_balance: float
    transactions_count: int


class StockReport(BaseModel):
    period: str
    start_date: date
    end_date: date
    opening_stock: float
    closing_stock: float
    total_stock_in: float
    total_stock_out: float
    daily_breakdown: List[StockReportItem]


def get_or_create_current_stock(db: Session) -> CurrentStock:
    """Get or create current stock record"""
    stock = db.query(CurrentStock).first()
    if not stock:
        stock = CurrentStock(total_liters=Decimal("0"))
        db.add(stock)
        db.commit()
        db.refresh(stock)
    return stock


@router.get("/current", response_model=CurrentStockResponse)
def get_current_stock(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get current stock level"""
    stock = get_or_create_current_stock(db)
    return CurrentStockResponse(
        total_liters=float(stock.total_liters),
        last_updated=stock.last_updated
    )


@router.get("/summary", response_model=StockSummary)
def get_stock_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get stock summary with totals (Admin only)"""
    stock = get_or_create_current_stock(db)
    
    stock_in_result = db.query(
        func.coalesce(func.sum(StockTransaction.liters), 0),
        func.coalesce(func.sum(StockTransaction.total_amount), 0)
    ).filter(StockTransaction.transaction_type == StockTransactionType.STOCK_IN).first()
    
    stock_out_result = db.query(
        func.coalesce(func.sum(StockTransaction.liters), 0),
        func.coalesce(func.sum(StockTransaction.total_amount), 0)
    ).filter(StockTransaction.transaction_type == StockTransactionType.STOCK_OUT).first()
    
    return StockSummary(
        current_stock=float(stock.total_liters),
        total_stock_in=float(stock_in_result[0]),
        total_stock_out=float(stock_out_result[0]),
        total_purchase_amount=float(stock_in_result[1]),
        total_sales_amount=float(stock_out_result[1]),
        last_updated=stock.last_updated
    )


@router.post("/transaction", response_model=StockTransactionResponse)
def create_stock_transaction(
    request: StockTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a stock transaction (Admin only)"""
    try:
        transaction_type = StockTransactionType(request.transaction_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transaction type. Use 'stock_in' or 'stock_out'")
    
    stock = get_or_create_current_stock(db)
    
    if transaction_type == StockTransactionType.STOCK_OUT:
        if float(stock.total_liters) < request.liters:
            raise HTTPException(status_code=400, detail=f"Insufficient stock. Available: {stock.total_liters} liters")
    
    transaction = StockTransaction(
        transaction_type=transaction_type,
        liters=Decimal(str(request.liters)),
        rate_per_liter=Decimal(str(request.rate_per_liter)) if request.rate_per_liter else None,
        total_amount=Decimal(str(request.total_amount)) if request.total_amount else None,
        supplier_name=request.supplier_name,
        vehicle_number=request.vehicle_number,
        invoice_number=request.invoice_number,
        notes=request.notes,
        recorded_by=current_user.id,
        transaction_date=request.transaction_date or datetime.utcnow()
    )
    
    if transaction_type == StockTransactionType.STOCK_IN:
        stock.total_liters = Decimal(str(float(stock.total_liters) + request.liters))
    else:
        stock.total_liters = Decimal(str(float(stock.total_liters) - request.liters))
    
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    
    return StockTransactionResponse(
        id=transaction.id,
        transaction_type=transaction.transaction_type.value,
        liters=float(transaction.liters),
        rate_per_liter=float(transaction.rate_per_liter) if transaction.rate_per_liter else None,
        total_amount=float(transaction.total_amount) if transaction.total_amount else None,
        supplier_name=transaction.supplier_name,
        vehicle_number=transaction.vehicle_number,
        invoice_number=transaction.invoice_number,
        order_id=transaction.order_id,
        notes=transaction.notes,
        recorded_by=transaction.recorded_by,
        recorded_by_name=current_user.name,
        transaction_date=transaction.transaction_date,
        created_at=transaction.created_at
    )


@router.get("/transactions", response_model=List[StockTransactionResponse])
def get_stock_transactions(
    transaction_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get stock transaction history (Admin only)"""
    query = db.query(StockTransaction)
    
    if transaction_type:
        try:
            t_type = StockTransactionType(transaction_type)
            query = query.filter(StockTransaction.transaction_type == t_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid transaction type")
    
    if start_date:
        query = query.filter(StockTransaction.transaction_date >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(StockTransaction.transaction_date <= datetime.combine(end_date, datetime.max.time()))
    
    transactions = query.order_by(StockTransaction.transaction_date.desc()).offset(offset).limit(limit).all()
    
    result = []
    for t in transactions:
        user = db.query(User).filter(User.id == t.recorded_by).first()
        result.append(StockTransactionResponse(
            id=t.id,
            transaction_type=t.transaction_type.value,
            liters=float(t.liters),
            rate_per_liter=float(t.rate_per_liter) if t.rate_per_liter else None,
            total_amount=float(t.total_amount) if t.total_amount else None,
            supplier_name=t.supplier_name,
            vehicle_number=t.vehicle_number,
            invoice_number=t.invoice_number,
            order_id=t.order_id,
            notes=t.notes,
            recorded_by=t.recorded_by,
            recorded_by_name=user.name if user else None,
            transaction_date=t.transaction_date,
            created_at=t.created_at
        ))
    
    return result


@router.get("/report", response_model=StockReport)
def get_stock_report(
    period: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get stock in/out report with daily breakdown (Admin only)"""
    today = date.today()
    
    if period == "daily":
        start_date = today
        end_date = today
    elif period == "weekly":
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    else:
        start_date = today.replace(day=1)
        end_date = today
    
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    transactions = db.query(StockTransaction).filter(
        and_(
            StockTransaction.transaction_date >= start_datetime,
            StockTransaction.transaction_date <= end_datetime
        )
    ).order_by(StockTransaction.transaction_date).all()
    
    stock_before = db.query(func.coalesce(func.sum(
        func.case(
            (StockTransaction.transaction_type == StockTransactionType.STOCK_IN, StockTransaction.liters),
            else_=-StockTransaction.liters
        )
    ), 0)).filter(StockTransaction.transaction_date < start_datetime).scalar()
    
    opening_stock = float(stock_before)
    
    total_in = sum(float(t.liters) for t in transactions if t.transaction_type == StockTransactionType.STOCK_IN)
    total_out = sum(float(t.liters) for t in transactions if t.transaction_type == StockTransactionType.STOCK_OUT)
    closing_stock = opening_stock + total_in - total_out
    
    daily_data = {}
    running_balance = opening_stock
    
    current_date = start_date
    while current_date <= end_date:
        daily_data[current_date] = {
            'stock_in': 0.0,
            'stock_out': 0.0,
            'opening_balance': running_balance,
            'transactions_count': 0
        }
        current_date += timedelta(days=1)
    
    for t in transactions:
        t_date = t.transaction_date.date()
        if t_date in daily_data:
            if t.transaction_type == StockTransactionType.STOCK_IN:
                daily_data[t_date]['stock_in'] += float(t.liters)
            else:
                daily_data[t_date]['stock_out'] += float(t.liters)
            daily_data[t_date]['transactions_count'] += 1
    
    running_balance = opening_stock
    for d in sorted(daily_data.keys()):
        daily_data[d]['opening_balance'] = running_balance
        running_balance = running_balance + daily_data[d]['stock_in'] - daily_data[d]['stock_out']
        daily_data[d]['closing_balance'] = running_balance
    
    daily_breakdown = [
        StockReportItem(
            date=d,
            stock_in=data['stock_in'],
            stock_out=data['stock_out'],
            opening_balance=data['opening_balance'],
            closing_balance=data['closing_balance'],
            transactions_count=data['transactions_count']
        )
        for d, data in sorted(daily_data.items(), reverse=True)
    ]
    
    return StockReport(
        period=period,
        start_date=start_date,
        end_date=end_date,
        opening_stock=opening_stock,
        closing_stock=closing_stock,
        total_stock_in=total_in,
        total_stock_out=total_out,
        daily_breakdown=daily_breakdown
    )


@router.post("/sync-from-orders")
def sync_stock_from_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Sync stock out from delivered orders (Admin only) - One time utility"""
    delivered_orders = db.query(Order).filter(Order.status == OrderStatus.DELIVERED).all()
    
    synced_count = 0
    for order in delivered_orders:
        existing = db.query(StockTransaction).filter(
            StockTransaction.order_id == order.id
        ).first()
        
        if not existing and order.liters:
            transaction = StockTransaction(
                transaction_type=StockTransactionType.STOCK_OUT,
                liters=Decimal(str(order.liters)),
                rate_per_liter=Decimal(str(order.rate)) if order.rate else None,
                total_amount=Decimal(str(order.amount)) if order.amount else None,
                order_id=order.id,
                notes=f"Auto-synced from order #{order.id}",
                recorded_by=current_user.id,
                transaction_date=order.updated_at or order.created_at
            )
            db.add(transaction)
            synced_count += 1
    
    if synced_count > 0:
        total_out = db.query(func.sum(StockTransaction.liters)).filter(
            StockTransaction.transaction_type == StockTransactionType.STOCK_OUT
        ).scalar() or 0
        
        total_in = db.query(func.sum(StockTransaction.liters)).filter(
            StockTransaction.transaction_type == StockTransactionType.STOCK_IN
        ).scalar() or 0
        
        stock = get_or_create_current_stock(db)
        stock.total_liters = Decimal(str(float(total_in) - float(total_out)))
        
    db.commit()
    
    return {"message": f"Synced {synced_count} orders to stock transactions"}
