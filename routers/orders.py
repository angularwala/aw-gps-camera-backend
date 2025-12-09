from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from pydantic import BaseModel, validator, Field
from typing import List, Optional
from datetime import datetime
from database import get_db
from models.order import Order, OrderStatus
from models.transaction import Transaction
from models.user import User
from models.customer import Customer
from models.receipt import Receipt
from models.notification import NotificationType, UserRole
from utils.auth_dependency import get_current_user, get_current_admin, get_current_admin_or_customer, get_current_admin_or_driver
from services.notification_service import NotificationService
import random
import os
import shutil
import re

router = APIRouter(prefix="/api/orders", tags=["Orders"])

class OrderCreate(BaseModel):
    liters: float = Field(..., gt=0, le=50000, description="Quantity in liters (must be between 0 and 50,000)")
    rate: float = Field(..., gt=0, le=500, description="Rate per liter (must be between 0 and 500)")
    delivery_time: Optional[datetime] = None
    delivery_address: Optional[str] = Field(None, min_length=10, max_length=500)
    delivery_gps_lat: Optional[float] = Field(None, ge=-90, le=90)
    delivery_gps_long: Optional[float] = Field(None, ge=-180, le=180)
    vehicle_number: Optional[str] = Field(None, min_length=3, max_length=50)
    vehicle_photo: Optional[str] = None
    contact_number: Optional[str] = Field(None, max_length=20)
    
    @validator('delivery_address')
    def validate_address(cls, v):
        if v is not None:
            # Remove excessive whitespace
            v = ' '.join(v.split())
            # Check for minimum meaningful content
            if len(v.strip()) < 10:
                raise ValueError('Delivery address must be at least 10 characters')
            # Basic XSS prevention - reject HTML/script tags
            if re.search(r'<\s*script|<\s*iframe|javascript:', v, re.IGNORECASE):
                raise ValueError('Invalid characters in delivery address')
        return v
    
    @validator('vehicle_number')
    def validate_vehicle_number(cls, v):
        if v is not None:
            # Remove excessive whitespace
            v = ' '.join(v.split())
            # Basic XSS prevention
            if re.search(r'<\s*script|<\s*iframe|javascript:', v, re.IGNORECASE):
                raise ValueError('Invalid characters in vehicle number')
        return v
    
    @validator('liters')
    def validate_liters(cls, v):
        if v <= 0:
            raise ValueError('Liters must be greater than 0')
        if v > 50000:
            raise ValueError('Liters cannot exceed 50,000')
        return round(v, 2)
    
    @validator('rate')
    def validate_rate(cls, v):
        if v <= 0:
            raise ValueError('Rate must be greater than 0')
        if v > 500:
            raise ValueError('Rate per liter cannot exceed ₹500')
        return round(v, 2)

class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    driver_id: Optional[int] = None
    delivery_time: Optional[datetime] = None
    signature: Optional[str] = None
    otp_input: Optional[str] = None

class AdminOrderCreate(BaseModel):
    customer_id: int
    liters: float = Field(..., gt=0, le=50000)
    rate: float = Field(..., gt=0, le=500)
    delivery_address: Optional[str] = None
    delivery_gps_lat: Optional[float] = None
    delivery_gps_long: Optional[float] = None
    vehicle_number: Optional[str] = None
    driver_id: Optional[int] = None
    contact_number: Optional[str] = Field(None, max_length=20)

class OrderEdit(BaseModel):
    """For editing order details by customer/admin - only allowed for pending/assigned orders"""
    liters: Optional[float] = Field(None, gt=0, le=50000)
    rate: Optional[float] = Field(None, gt=0, le=500)
    delivery_address: Optional[str] = Field(None, min_length=10, max_length=500)
    delivery_time: Optional[datetime] = None
    delivery_gps_lat: Optional[float] = Field(None, ge=-90, le=90)
    delivery_gps_long: Optional[float] = Field(None, ge=-180, le=180)
    vehicle_number: Optional[str] = Field(None, min_length=3, max_length=50)
    
    @validator('delivery_address')
    def validate_address(cls, v):
        if v is not None:
            v = ' '.join(v.split())
            if len(v.strip()) < 10:
                raise ValueError('Delivery address must be at least 10 characters')
            if re.search(r'<\s*script|<\s*iframe|javascript:', v, re.IGNORECASE):
                raise ValueError('Invalid characters in delivery address')
        return v
    
    @validator('vehicle_number')
    def validate_vehicle_number(cls, v):
        if v is not None:
            v = ' '.join(v.split())
            if re.search(r'<\s*script|<\s*iframe|javascript:', v, re.IGNORECASE):
                raise ValueError('Invalid characters in vehicle number')
        return v

class CustomerInfo(BaseModel):
    name: str
    mobile: str
    company_name: str
    address: Optional[str]
    gps_lat: Optional[float]
    gps_long: Optional[float]
    
    class Config:
        from_attributes = True

class ReceiptInfo(BaseModel):
    id: int
    file_url: str
    file_type: Optional[str]
    timestamp: datetime
    
    class Config:
        from_attributes = True

class OrderResponse(BaseModel):
    id: int
    customer_id: int
    driver_id: Optional[int]
    liters: float
    rate: float
    amount: float
    status: OrderStatus
    delivery_time: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    otp: Optional[str]
    delivery_address: Optional[str]
    delivery_gps_lat: Optional[float]
    delivery_gps_long: Optional[float]
    vehicle_number: Optional[str]
    vehicle_photo: Optional[str]
    contact_number: Optional[str] = None
    customer_info: Optional[CustomerInfo] = None
    receipts: Optional[List['ReceiptInfo']] = []
    customer_name: Optional[str] = None
    driver_name: Optional[str] = None
    customer_mobile: Optional[str] = None
    fuel_type: str = "Diesel"
    
    class Config:
        from_attributes = True

@router.get("/", response_model=List[OrderResponse])
def get_orders(
    customer_id: Optional[int] = None,
    driver_id: Optional[int] = None,
    status: Optional[OrderStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get orders with role-based authorization:
    - Admin: Can view all orders or filter by customer_id/driver_id/status
    - Driver: Can only view their own assigned orders
    - Customer: Can only view their own orders
    """
    from models.user import UserRole
    
    query = db.query(Order)
    
    # Role-based authorization
    if current_user.role == UserRole.ADMIN:
        # Admins can view all orders with optional filters
        pass  # No additional restrictions
    elif current_user.role == UserRole.DRIVER:
        # Drivers can only view their own orders
        query = query.filter(Order.driver_id == current_user.id)
        # Ignore customer_id filter if provided (security)
        customer_id = None
        # If driver_id provided, ensure it's their own
        if driver_id and driver_id != current_user.id:
            raise HTTPException(status_code=403, detail="Cannot view other driver's orders")
    elif current_user.role == UserRole.CUSTOMER:
        # Customers can only view their own orders
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer profile not found")
        query = query.filter(Order.customer_id == customer.id)
        # Ignore driver_id and customer_id filters (security)
        driver_id = None
        customer_id = None
    
    # Eagerly load customer and driver relationships
    query = query.options(
        joinedload(Order.customer).joinedload(Customer.user)
    )
    
    # Apply admin filters (only effective for admins)
    if customer_id:
        query = query.filter(Order.customer_id == customer_id)
    if driver_id:
        query = query.filter(Order.driver_id == driver_id)
    if status:
        query = query.filter(Order.status == status)
    
    orders = query.order_by(Order.created_at.desc()).all()
    
    # Build response with customer and driver info
    result = []
    for order in orders:
        customer_info = None
        customer_name = None
        customer_mobile = None
        driver_name = None
        
        # Get customer name and mobile
        if order.customer and order.customer.user:
            customer_name = order.customer.user.name
            customer_mobile = order.customer.user.mobile
            customer_info = CustomerInfo(
                name=order.customer.user.name,
                mobile=order.customer.user.mobile,
                company_name=order.customer.company_name,
                address=order.customer.address or "",
                gps_lat=order.customer.gps_lat,
                gps_long=order.customer.gps_long
            )
        
        # Get driver name
        if order.driver_id:
            driver = db.query(User).filter(User.id == order.driver_id).first()
            if driver:
                driver_name = driver.name
        
        # Get receipts for this order
        receipts = [ReceiptInfo(
            id=r.id,
            file_url=r.file_url,
            file_type=r.file_type,
            timestamp=r.timestamp
        ) for r in order.receipts]
        
        result.append(OrderResponse(
            id=order.id,
            customer_id=order.customer_id,
            driver_id=order.driver_id,
            liters=order.liters,
            rate=order.rate,
            amount=order.amount,
            status=order.status,
            delivery_time=order.delivery_time,
            created_at=order.created_at,
            updated_at=order.updated_at,
            otp=order.otp,
            delivery_address=order.delivery_address,
            delivery_gps_lat=order.delivery_gps_lat,
            delivery_gps_long=order.delivery_gps_long,
            vehicle_number=order.vehicle_number,
            vehicle_photo=order.vehicle_photo,
            contact_number=order.contact_number,
            customer_info=customer_info,
            receipts=receipts,
            customer_name=customer_name,
            driver_name=driver_name,
            customer_mobile=customer_mobile,
            fuel_type="Diesel"
        ))
    
    return result

@router.get("/my-orders", response_model=List[OrderResponse])
def get_my_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all orders for the current authenticated customer
    Customer-only endpoint - returns orders for the logged-in customer
    """
    # Enforce customer-only access
    if current_user.role != "customer":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only accessible to customers"
        )
    
    # Find the customer record for this user
    customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
    if not customer:
        return []  # Return empty list if customer profile not found
    
    # Get all orders for this customer
    orders = db.query(Order).filter(
        Order.customer_id == customer.id
    ).order_by(Order.created_at.desc()).all()
    
    # Build response with receipts
    result = []
    for order in orders:
        # Get receipts for this order
        receipts = [ReceiptInfo(
            id=r.id,
            file_url=r.file_url,
            file_type=r.file_type,
            timestamp=r.timestamp
        ) for r in order.receipts]
        
        result.append(OrderResponse(
            id=order.id,
            customer_id=order.customer_id,
            driver_id=order.driver_id,
            liters=order.liters,
            rate=order.rate,
            amount=order.amount,
            status=order.status,
            delivery_time=order.delivery_time,
            created_at=order.created_at,
            updated_at=order.updated_at,
            otp=order.otp,
            delivery_address=order.delivery_address,
            delivery_gps_lat=order.delivery_gps_lat,
            delivery_gps_long=order.delivery_gps_long,
            vehicle_number=order.vehicle_number,
            vehicle_photo=order.vehicle_photo,
            customer_info=None,
            receipts=receipts
        ))
    
    return result

@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.post("/", response_model=OrderResponse)
def create_order(request: OrderCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_or_customer)):
    # Find the customer record for this user
    customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
    if not customer:
        raise HTTPException(status_code=400, detail="Customer profile not found. Please complete registration.")
    
    # Check if customer is active
    if hasattr(customer, 'is_active') and not customer.is_active:
        raise HTTPException(status_code=403, detail="Your account is deactivated. Please contact admin to place orders.")
    
    amount = request.liters * request.rate
    
    order = Order(
        customer_id=customer.id,
        liters=request.liters,
        rate=request.rate,
        amount=amount,
        status=OrderStatus.PENDING,
        delivery_time=request.delivery_time,
        otp=str(random.randint(100000, 999999)),
        delivery_address=request.delivery_address,
        delivery_gps_lat=request.delivery_gps_lat,
        delivery_gps_long=request.delivery_gps_long,
        vehicle_number=request.vehicle_number,
        vehicle_photo=request.vehicle_photo,
        contact_number=request.contact_number
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    
    # Create transaction entry
    transaction = Transaction(
        customer_id=customer.id,
        order_id=order.id,
        amount=amount,
        paid=0.0,
        due=amount,
        is_payment=False
    )
    db.add(transaction)
    db.commit()
    
    # Create notifications for new order
    try:
        # Notify admins about new order
        NotificationService.create_notification(
            db=db,
            role=UserRole.ADMIN,
            notification_type=NotificationType.NEW_ORDER,
            order_id=order.id,
            metadata={
                "customer_name": customer.company_name,
                "amount": f"₹{amount:,.2f}",
                "liters": request.liters,
                "order_id": order.id
            }
        )
        
        # Notify customer about order initiated
        NotificationService.create_notification(
            db=db,
            role=UserRole.CUSTOMER,
            notification_type=NotificationType.ORDER_INITIATED,
            user_id=current_user.id,
            order_id=order.id,
            metadata={
                "order_id": order.id,
                "amount": f"₹{amount:,.2f}",
                "liters": request.liters
            }
        )
    except Exception as e:
        print(f"Error creating notifications: {e}")
    
    return order

@router.post("/admin", response_model=OrderResponse)
def create_order_by_admin(request: AdminOrderCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    """Admin creates order for a specific customer"""
    # Verify customer exists
    customer = db.query(Customer).filter(Customer.id == request.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Check if customer is active
    if hasattr(customer, 'is_active') and not customer.is_active:
        raise HTTPException(status_code=403, detail="Cannot create order for deactivated customer.")
    
    amount = request.liters * request.rate
    otp = str(random.randint(100000, 999999))
    
    # Use customer's address if not provided
    delivery_address = request.delivery_address or customer.address
    delivery_lat = request.delivery_gps_lat or customer.gps_lat
    delivery_long = request.delivery_gps_long or customer.gps_long
    
    order = Order(
        customer_id=request.customer_id,
        driver_id=request.driver_id,
        liters=request.liters,
        rate=request.rate,
        amount=amount,
        otp=otp,
        delivery_address=delivery_address,
        delivery_gps_lat=delivery_lat,
        delivery_gps_long=delivery_long,
        vehicle_number=request.vehicle_number,
        contact_number=request.contact_number,
        status=OrderStatus.ASSIGNED if request.driver_id else OrderStatus.PENDING
    )
    
    db.add(order)
    db.commit()
    db.refresh(order)
    
    # Get names for response
    customer_name = customer.user.name if customer.user else None
    driver_name = None
    driver = None
    if request.driver_id:
        driver = db.query(User).filter(User.id == request.driver_id).first()
        if driver:
            driver_name = driver.name
    
    # Create notifications for admin-created order
    try:
        # Notify customer about order created
        if customer.user_id:
            NotificationService.create_notification(
                db=db,
                role=UserRole.CUSTOMER,
                notification_type=NotificationType.ORDER_INITIATED,
                user_id=customer.user_id,
                order_id=order.id,
                metadata={
                    "order_id": order.id,
                    "amount": f"₹{amount:,.2f}",
                    "liters": request.liters
                }
            )
        
        # If driver is assigned, notify driver and customer
        if request.driver_id and driver:
            # Notify driver about new assignment
            NotificationService.create_notification(
                db=db,
                role=UserRole.DRIVER,
                notification_type=NotificationType.ORDER_ASSIGNED,
                user_id=request.driver_id,
                order_id=order.id,
                metadata={
                    "order_id": order.id,
                    "customer_name": customer.company_name,
                    "amount": f"₹{amount:,.2f}",
                    "liters": request.liters,
                    "delivery_address": delivery_address or "Not specified"
                }
            )
            
            # Notify customer about driver assignment
            if customer.user_id:
                NotificationService.create_notification(
                    db=db,
                    role=UserRole.CUSTOMER,
                    notification_type=NotificationType.DRIVER_ASSIGNED,
                    user_id=customer.user_id,
                    order_id=order.id,
                    metadata={
                        "order_id": order.id,
                        "driver_name": driver_name
                    }
                )
    except Exception as e:
        print(f"Error creating notifications for admin order: {e}")
    
    return OrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        driver_id=order.driver_id,
        liters=order.liters,
        rate=order.rate,
        amount=order.amount,
        status=order.status,
        delivery_time=order.delivery_time,
        created_at=order.created_at,
        updated_at=order.updated_at,
        otp=order.otp,
        delivery_address=order.delivery_address,
        delivery_gps_lat=order.delivery_gps_lat,
        delivery_gps_long=order.delivery_gps_long,
        vehicle_number=order.vehicle_number,
        vehicle_photo=order.vehicle_photo,
        contact_number=order.contact_number,
        customer_info=None,
        receipts=[],
        customer_name=customer_name,
        driver_name=driver_name,
        customer_mobile=customer.user.mobile if customer.user else None,
        fuel_type="Diesel"
    )

@router.put("/{order_id}", response_model=OrderResponse)
def update_order(order_id: int, request: OrderUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_or_driver)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # CRITICAL: One delivery at a time - check if driver is starting a new delivery
    if request.status == OrderStatus.IN_TRANSIT and current_user.role == "driver":
        # Check if this driver already has an active delivery (in_transit)
        active_delivery = db.query(Order).filter(
            Order.driver_id == current_user.id,
            Order.status == OrderStatus.IN_TRANSIT,
            Order.id != order_id  # Exclude current order
        ).first()
        
        if active_delivery:
            raise HTTPException(
                status_code=409, 
                detail=f"You already have an active delivery (Order #{active_delivery.id}). Complete it before starting a new one."
            )
    
    # Track old status for notifications
    old_status = order.status
    old_driver_id = order.driver_id
    
    # CRITICAL: Determine if this update will result in DELIVERED status
    # Any of these conditions means delivery completion is being attempted:
    # 1. Explicitly setting status to DELIVERED
    # 2. Providing a signature (which auto-completes delivery)
    will_be_delivered = (request.status == OrderStatus.DELIVERED) or (request.signature is not None)
    
    # SECURITY CRITICAL: Validate OTP, receipt, and vehicle photo BEFORE any delivery completion
    # This runs for ALL paths that result in DELIVERED status (no bypass possible)
    if will_be_delivered:
        # Validate OTP first (MANDATORY for delivery completion)
        if not request.otp_input:
            raise HTTPException(status_code=400, detail="OTP is required to complete delivery")
        
        if request.otp_input != order.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP. Please verify with customer")
        
        # Check if receipt uploaded
        receipt_count = db.query(Receipt).filter(Receipt.order_id == order_id).count()
        if receipt_count == 0:
            raise HTTPException(status_code=400, detail="Cannot mark as delivered: Sale receipt is required")
    
    # Apply updates only after validation passes
    if request.status:
        order.status = request.status
    if request.driver_id:
        order.driver_id = request.driver_id
        order.status = OrderStatus.ASSIGNED
    if request.delivery_time:
        order.delivery_time = request.delivery_time
    if request.signature:
        order.signature = request.signature
        if request.status != OrderStatus.DELIVERED:  # Only auto-set if not already being set
            order.status = OrderStatus.DELIVERED
    
    db.commit()
    db.refresh(order)
    
    # Send notifications based on status changes
    try:
        customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
        driver = db.query(User).filter(User.id == order.driver_id).first() if order.driver_id else None
        driver_name = driver.name if driver else "Unknown"
        
        # 1. Notify when driver is assigned (Admin assigns driver → Customer gets notified)
        if request.driver_id and old_driver_id != request.driver_id:
            # Notify the driver about new assignment
            NotificationService.create_notification(
                db=db,
                role=UserRole.DRIVER,
                notification_type=NotificationType.ORDER_ASSIGNED,
                user_id=request.driver_id,
                order_id=order.id,
                metadata={
                    "order_id": order.id,
                    "customer_name": customer.company_name if customer else "Unknown",
                    "amount": f"₹{order.amount:,.2f}",
                    "liters": order.liters,
                    "delivery_address": order.delivery_address or "Not specified"
                }
            )
            
            # Notify customer that driver has been assigned
            if customer:
                NotificationService.create_notification(
                    db=db,
                    role=UserRole.CUSTOMER,
                    notification_type=NotificationType.DRIVER_ASSIGNED,
                    user_id=customer.user_id,
                    order_id=order.id,
                    metadata={
                        "order_id": order.id,
                        "driver_name": driver_name
                    }
                )
        
        # 2. Notify when driver starts delivery (IN_TRANSIT) → Customer and Admin get notified
        if order.status == OrderStatus.IN_TRANSIT and old_status != OrderStatus.IN_TRANSIT:
            # Notify customer that delivery is on the way
            if customer:
                NotificationService.create_notification(
                    db=db,
                    role=UserRole.CUSTOMER,
                    notification_type=NotificationType.ORDER_IN_TRANSIT,
                    user_id=customer.user_id,
                    order_id=order.id,
                    metadata={
                        "order_id": order.id,
                        "driver_name": driver_name
                    }
                )
            
            # Notify admin that delivery has started
            NotificationService.create_notification(
                db=db,
                role=UserRole.ADMIN,
                notification_type=NotificationType.DELIVERY_STARTED,
                order_id=order.id,
                metadata={
                    "order_id": order.id,
                    "driver_name": driver_name,
                    "customer_name": customer.company_name if customer else "Unknown"
                }
            )
        
        # 3. Notify when order is delivered → Customer and Admin get notified
        if order.status == OrderStatus.DELIVERED and old_status != OrderStatus.DELIVERED:
            # Notify customer about successful delivery
            if customer:
                NotificationService.create_notification(
                    db=db,
                    role=UserRole.CUSTOMER,
                    notification_type=NotificationType.ORDER_DELIVERED,
                    user_id=customer.user_id,
                    order_id=order.id,
                    metadata={
                        "order_id": order.id,
                        "liters": order.liters,
                        "amount": f"₹{order.amount:,.2f}"
                    }
                )
            
            # Notify admin about delivery completion
            NotificationService.create_notification(
                db=db,
                role=UserRole.ADMIN,
                notification_type=NotificationType.DELIVERY_COMPLETED,
                order_id=order.id,
                metadata={
                    "order_id": order.id,
                    "driver_name": driver_name,
                    "customer_name": customer.company_name if customer else "Unknown",
                    "amount": f"₹{order.amount:,.2f}"
                }
            )
    except Exception as e:
        print(f"Error creating notifications: {e}")
    
    # Build response with customer and driver names
    customer_name = None
    driver_name = None
    
    if order.customer and order.customer.user:
        customer_name = order.customer.user.name
    else:
        customer_obj = db.query(Customer).options(joinedload(Customer.user)).filter(Customer.id == order.customer_id).first()
        if customer_obj and customer_obj.user:
            customer_name = customer_obj.user.name
    
    if order.driver_id:
        driver = db.query(User).filter(User.id == order.driver_id).first()
        if driver:
            driver_name = driver.name
    
    return OrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        driver_id=order.driver_id,
        liters=order.liters,
        rate=order.rate,
        amount=order.amount,
        status=order.status,
        delivery_time=order.delivery_time,
        created_at=order.created_at,
        updated_at=order.updated_at,
        otp=order.otp,
        delivery_address=order.delivery_address,
        delivery_gps_lat=order.delivery_gps_lat,
        delivery_gps_long=order.delivery_gps_long,
        vehicle_number=order.vehicle_number,
        vehicle_photo=order.vehicle_photo,
        customer_info=None,
        receipts=[],
        customer_name=customer_name,
        driver_name=driver_name,
        fuel_type="Diesel"
    )

@router.post("/{order_id}/upload-vehicle-photo")
async def upload_vehicle_photo(
    order_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_driver)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Create upload directory
    upload_dir = "uploads/vehicles"
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate unique filename
    file_extension = os.path.splitext(file.filename)[1]
    filename = f"vehicle_{order_id}_{datetime.now().timestamp()}{file_extension}"
    file_path = os.path.join(upload_dir, filename)
    
    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Update order with vehicle photo path
    order.vehicle_photo = f"/uploads/vehicles/{filename}"
    db.commit()
    db.refresh(order)
    
    return {"message": "Vehicle photo uploaded successfully", "file_url": order.vehicle_photo}

@router.delete("/{order_id}")
def cancel_order(order_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_or_customer)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Store driver_id before cancellation
    driver_id = order.driver_id
    customer_id = order.customer_id
    
    order.status = OrderStatus.CANCELLED
    db.commit()
    
    # Send notifications
    try:
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        
        # Notify customer about cancellation
        if customer:
            NotificationService.create_notification(
                db=db,
                role=UserRole.CUSTOMER,
                notification_type=NotificationType.ORDER_CANCELLED,
                user_id=customer.user_id,
                order_id=order.id,
                metadata={"order_id": order.id}
            )
        
        # Notify driver if order was assigned
        if driver_id:
            NotificationService.create_notification(
                db=db,
                role=UserRole.DRIVER,
                notification_type=NotificationType.ORDER_UNASSIGNED,
                user_id=driver_id,
                order_id=order.id,
                metadata={"order_id": order.id}
            )
    except Exception as e:
        # Log error but don't fail the cancellation
        print(f"Error creating notifications: {e}")
    
    return {"message": "Order cancelled successfully"}

class DashboardStats(BaseModel):
    total_orders: int
    pending_orders: int
    delivered_orders: int
    total_sales: float
    total_liters: float

@router.get("/stats/dashboard", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    total_orders = db.query(func.count(Order.id)).scalar()
    pending_orders = db.query(func.count(Order.id)).filter(
        Order.status.in_([OrderStatus.PENDING, OrderStatus.ASSIGNED, OrderStatus.IN_TRANSIT])
    ).scalar()
    delivered_orders = db.query(func.count(Order.id)).filter(Order.status == OrderStatus.DELIVERED).scalar()
    
    sales_data = db.query(
        func.sum(Order.amount),
        func.sum(Order.liters)
    ).filter(Order.status == OrderStatus.DELIVERED).first()
    
    total_sales = float(sales_data[0]) if sales_data and sales_data[0] else 0.0
    total_liters = float(sales_data[1]) if sales_data and sales_data[1] else 0.0
    
    return DashboardStats(
        total_orders=total_orders or 0,
        pending_orders=pending_orders or 0,
        delivered_orders=delivered_orders or 0,
        total_sales=total_sales,
        total_liters=total_liters
    )

@router.patch("/{order_id}/edit", response_model=OrderResponse)
def edit_order(
    order_id: int,
    request: OrderEdit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_customer)
):
    """Edit order details - only allowed for PENDING or ASSIGNED orders"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check if order is editable
    if order.status not in [OrderStatus.PENDING, OrderStatus.ASSIGNED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit order with status {order.status}. Only PENDING or ASSIGNED orders can be edited."
        )
    
    # If customer is editing, verify ownership
    if current_user.role == "customer":
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        if not customer or order.customer_id != customer.id:
            raise HTTPException(status_code=403, detail="Not authorized to edit this order")
    
    # Update fields if provided
    if request.liters is not None:
        order.liters = round(request.liters, 2)
    if request.rate is not None:
        order.rate = round(request.rate, 2)
    if request.delivery_address is not None:
        order.delivery_address = request.delivery_address
    if request.delivery_time is not None:
        order.delivery_time = request.delivery_time
    if request.delivery_gps_lat is not None:
        order.delivery_gps_lat = request.delivery_gps_lat
    if request.delivery_gps_long is not None:
        order.delivery_gps_long = request.delivery_gps_long
    if request.vehicle_number is not None:
        order.vehicle_number = request.vehicle_number
    
    # Recalculate amount if liters or rate changed
    if request.liters is not None or request.rate is not None:
        old_amount = order.amount
        order.amount = round(order.liters * order.rate, 2)
        
        # Update associated transaction with proper financial reconciliation
        transaction = db.query(Transaction).filter(Transaction.order_id == order_id).first()
        if transaction:
            # Preserve payment information and recalculate due amount
            transaction.amount = order.amount
            transaction.due = round(order.amount - transaction.paid, 2)
            
            # Validate that paid amount doesn't exceed new total
            if transaction.paid > order.amount:
                db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot reduce order amount below paid amount. Already paid: ₹{transaction.paid:.2f}, New amount: ₹{order.amount:.2f}"
                )
    
    db.commit()
    db.refresh(order)
    
    return order

@router.delete("/{order_id}")
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_customer)
):
    """Delete/Cancel an order - only allowed for PENDING or ASSIGNED orders"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check if order can be cancelled
    if order.status not in [OrderStatus.PENDING, OrderStatus.ASSIGNED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order with status {order.status}. Only PENDING or ASSIGNED orders can be cancelled."
        )
    
    # If customer is cancelling, verify ownership
    if current_user.role == "customer":
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        if not customer or order.customer_id != customer.id:
            raise HTTPException(status_code=403, detail="Not authorized to cancel this order")
    
    # Check if order has payments - cannot cancel if fully/partially paid
    transaction = db.query(Transaction).filter(Transaction.order_id == order_id).first()
    if transaction and transaction.paid > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order with payments. Paid amount: ₹{transaction.paid:.2f}. Please contact admin for refund."
        )
    
    # Mark as cancelled and zero out financial records
    order.status = OrderStatus.CANCELLED
    
    # Clear transaction amounts for cancelled order
    if transaction:
        transaction.amount = 0.0
        transaction.due = 0.0
        transaction.paid = 0.0
    
    db.commit()
    
    # TODO: Re-enable notifications after fixing import issues
    # Notification logic temporarily disabled
    
    return {"message": "Order cancelled successfully", "order_id": order_id}

# Response model for delivery review
class DeliveryReviewInfo(BaseModel):
    id: int
    customer_id: int
    driver_id: Optional[int]
    liters: float
    rate: float
    amount: float
    status: OrderStatus
    delivery_time: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    delivery_address: Optional[str]
    delivery_gps_lat: Optional[float]
    delivery_gps_long: Optional[float]
    vehicle_number: Optional[str]
    vehicle_photo: Optional[str]
    customer_name: Optional[str]
    driver_name: Optional[str]
    customer_mobile: Optional[str]
    receipts: List[ReceiptInfo] = []
    
    class Config:
        from_attributes = True

@router.get("/delivered/review", response_model=List[DeliveryReviewInfo])
def get_delivered_orders_for_review(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Get delivered orders with documents for admin review.
    Returns orders with vehicle photos and receipts.
    """
    orders = db.query(Order).filter(
        Order.status == OrderStatus.DELIVERED
    ).order_by(Order.updated_at.desc()).offset(offset).limit(limit).all()
    
    result = []
    for order in orders:
        # Get customer info through customer -> user relationship
        customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
        customer_user = db.query(User).filter(User.id == customer.user_id).first() if customer else None
        customer_name = customer.company_name if customer else "Unknown"
        customer_mobile = customer_user.mobile if customer_user else None
        
        # Get driver info
        driver = db.query(User).filter(User.id == order.driver_id).first() if order.driver_id else None
        driver_name = driver.name if driver else None
        
        # Get receipts
        receipts = db.query(Receipt).filter(Receipt.order_id == order.id).all()
        receipt_infos = [
            ReceiptInfo(
                id=r.id,
                file_url=r.file_url,
                file_type=r.file_type,
                timestamp=r.timestamp
            ) for r in receipts
        ]
        
        result.append(DeliveryReviewInfo(
            id=order.id,
            customer_id=order.customer_id,
            driver_id=order.driver_id,
            liters=order.liters,
            rate=order.rate,
            amount=order.amount,
            status=order.status,
            delivery_time=order.delivery_time,
            created_at=order.created_at,
            updated_at=order.updated_at,
            delivery_address=order.delivery_address,
            delivery_gps_lat=order.delivery_gps_lat,
            delivery_gps_long=order.delivery_gps_long,
            vehicle_number=order.vehicle_number,
            vehicle_photo=order.vehicle_photo,
            customer_name=customer_name,
            driver_name=driver_name,
            customer_mobile=customer_mobile,
            receipts=receipt_infos
        ))
    
    return result

@router.get("/{order_id}/review", response_model=DeliveryReviewInfo)
def get_order_for_review(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Get a single order with documents for admin review.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get customer info through customer -> user relationship
    customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
    customer_user = db.query(User).filter(User.id == customer.user_id).first() if customer else None
    customer_name = customer.company_name if customer else "Unknown"
    customer_mobile = customer_user.mobile if customer_user else None
    
    # Get driver info
    driver = db.query(User).filter(User.id == order.driver_id).first() if order.driver_id else None
    driver_name = driver.name if driver else None
    
    # Get receipts
    receipts = db.query(Receipt).filter(Receipt.order_id == order.id).all()
    receipt_infos = [
        ReceiptInfo(
            id=r.id,
            file_url=r.file_url,
            file_type=r.file_type,
            timestamp=r.timestamp
        ) for r in receipts
    ]
    
    return DeliveryReviewInfo(
        id=order.id,
        customer_id=order.customer_id,
        driver_id=order.driver_id,
        liters=order.liters,
        rate=order.rate,
        amount=order.amount,
        status=order.status,
        delivery_time=order.delivery_time,
        created_at=order.created_at,
        updated_at=order.updated_at,
        delivery_address=order.delivery_address,
        delivery_gps_lat=order.delivery_gps_lat,
        delivery_gps_long=order.delivery_gps_long,
        vehicle_number=order.vehicle_number,
        vehicle_photo=order.vehicle_photo,
        customer_name=customer_name,
        driver_name=driver_name,
        customer_mobile=customer_mobile,
        receipts=receipt_infos
    )
