from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from database import get_db
from models.customer import Customer
from models.user import User, UserRole
from models.order import Order, OrderStatus
from models.transaction import Transaction
from utils.security import get_password_hash
from utils.auth_dependency import get_current_admin, get_current_user

router = APIRouter(prefix="/api/customers", tags=["Customers"])

class CustomerResponse(BaseModel):
    id: int
    user_id: int
    company_name: str
    address: Optional[str]
    gps_lat: Optional[float]
    gps_long: Optional[float]
    name: str
    mobile: str
    is_active: bool = True
    email: Optional[str] = None
    gst_number: Optional[str] = None
    credit_limit: Optional[float] = None
    current_balance: Optional[float] = 0.0
    total_orders: Optional[int] = 0
    total_liters: Optional[float] = 0.0
    created_at: Optional[str] = None
    
    class Config:
        from_attributes = True

class CustomerStatusUpdate(BaseModel):
    is_active: bool

class CustomerCreate(BaseModel):
    name: str
    mobile: str
    password: str
    company_name: str
    address: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_long: Optional[float] = None

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    company_name: Optional[str] = None
    address: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_long: Optional[float] = None

class CustomerLocationUpdate(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None

def build_customer_response(customer: Customer, db: Session) -> CustomerResponse:
    """Build complete customer response with calculated stats"""
    total_orders = db.query(func.count(Order.id)).filter(
        Order.customer_id == customer.id
    ).scalar() or 0
    
    total_liters = db.query(func.sum(Order.liters)).filter(
        Order.customer_id == customer.id,
        Order.status == OrderStatus.DELIVERED
    ).scalar() or 0.0
    
    current_balance = db.query(func.sum(Transaction.amount)).filter(
        Transaction.customer_id == customer.id
    ).scalar() or 0.0
    
    return CustomerResponse(
        id=customer.id,
        user_id=customer.user_id,
        company_name=customer.company_name,
        address=customer.address,
        gps_lat=customer.gps_lat,
        gps_long=customer.gps_long,
        name=customer.user.name,
        mobile=customer.user.mobile,
        is_active=customer.is_active if hasattr(customer, 'is_active') else True,
        total_orders=total_orders,
        total_liters=float(total_liters),
        current_balance=float(current_balance),
        created_at=customer.created_at.isoformat() if customer.created_at else None
    )

@router.get("/", response_model=List[CustomerResponse])
def get_customers(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    """Get all customers - admin only"""
    customers = db.query(Customer).join(User).all()
    return [build_customer_response(c, db) for c in customers]

@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    return build_customer_response(customer, db)

@router.post("/", response_model=CustomerResponse)
def create_customer(request: CustomerCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    # Check if mobile exists
    existing_user = db.query(User).filter(User.mobile == request.mobile).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Mobile number already exists")
    
    # Create user
    user = User(
        name=request.name,
        mobile=request.mobile,
        password_hash=get_password_hash(request.password),
        role=UserRole.CUSTOMER
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create customer
    customer = Customer(
        user_id=user.id,
        company_name=request.company_name,
        address=request.address,
        gps_lat=request.gps_lat,
        gps_long=request.gps_long
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    
    return build_customer_response(customer, db)

@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(customer_id: int, request: CustomerUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if request.company_name:
        customer.company_name = request.company_name
    if request.address:
        customer.address = request.address
    if request.gps_lat is not None:
        customer.gps_lat = request.gps_lat
    if request.gps_long is not None:
        customer.gps_long = request.gps_long
    
    if request.name:
        customer.user.name = request.name
    
    db.commit()
    db.refresh(customer)
    
    return build_customer_response(customer, db)

@router.patch("/{customer_id}/status", response_model=CustomerResponse)
def update_customer_status(
    customer_id: int, 
    request: CustomerStatusUpdate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_admin)
):
    """Toggle customer active status. Admin only."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    customer.is_active = request.is_active
    db.commit()
    db.refresh(customer)
    
    return build_customer_response(customer, db)

@router.patch("/{customer_id}/location", response_model=CustomerResponse)
def update_customer_location(
    customer_id: int, 
    request: CustomerLocationUpdate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Update customer delivery location. Customers can only update their own location."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Security check: customers can only update their own location
    if current_user.role == UserRole.CUSTOMER:
        user_customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        if not user_customer or user_customer.id != customer_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this customer's location")
    
    # Validate coordinates
    if request.latitude < -90 or request.latitude > 90:
        raise HTTPException(status_code=400, detail="Invalid latitude. Must be between -90 and 90")
    if request.longitude < -180 or request.longitude > 180:
        raise HTTPException(status_code=400, detail="Invalid longitude. Must be between -180 and 180")
    
    customer.gps_lat = request.latitude
    customer.gps_long = request.longitude
    if request.address:
        customer.address = request.address
    
    db.commit()
    db.refresh(customer)
    
    return build_customer_response(customer, db)

@router.delete("/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    user = customer.user
    db.delete(customer)
    db.delete(user)
    db.commit()
    
    return {"message": "Customer deleted successfully"}
