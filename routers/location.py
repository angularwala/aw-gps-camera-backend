"""
Real-time location tracking endpoints for live truck tracking
Drivers send GPS updates, Admin/Customers receive live locations
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
from database import get_db
from models.truck_location import TruckLocation
from models.user import User
from models.order import Order, OrderStatus
from models.customer import Customer
from utils.auth_dependency import get_current_user, get_current_driver
from utils.logger import DatabaseLogger, LogCategory, LogLevel
from utils.distance import haversine_distance, calculate_eta
import json

router = APIRouter(prefix="/api/location", tags=["Location Tracking"])

def is_valid_india_location(latitude: float, longitude: float) -> bool:
    """
    Validates that coordinates are within India's geographic boundaries.
    Rejects test/dummy locations from outside service area.
    India bounds: Lat 6.5 to 35.5, Long 68 to 97.5
    """
    return 6.5 <= latitude <= 35.5 and 68.0 <= longitude <= 97.5

class LocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Latitude (-90 to 90)")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude (-180 to 180)")
    accuracy: Optional[float] = Field(None, description="GPS accuracy in meters")
    speed: Optional[float] = Field(None, description="Speed in km/h")
    heading: Optional[float] = Field(None, ge=0, le=360, description="Heading in degrees (0-360)")

class CurrentOrderInfo(BaseModel):
    id: int
    customer_name: Optional[str] = None
    customer_lat: Optional[float] = None
    customer_lng: Optional[float] = None
    liters: Optional[float] = None
    total_amount: Optional[float] = None
    delivery_address: Optional[str] = None
    status: Optional[str] = None

class LocationResponse(BaseModel):
    id: int
    driver_id: int
    driver_name: str
    driver_mobile: Optional[str] = None
    driver_phone: Optional[str] = None
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    timestamp: datetime
    time_ago: str
    distance_to_destination: Optional[float] = None
    eta_minutes: Optional[int] = None
    current_order: Optional[CurrentOrderInfo] = None
    
    class Config:
        from_attributes = True

# Store active WebSocket connections for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast location update to all connected clients"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass  # Client disconnected

manager = ConnectionManager()

@router.post("/update", response_model=LocationResponse)
async def update_location(
    location: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_driver)
):
    """
    Driver sends real-time GPS location update.
    Only accepts live GPS coordinates from driver devices within India.
    Rejects test/dummy locations from outside service area.
    """
    if not is_valid_india_location(location.latitude, location.longitude):
        raise HTTPException(
            status_code=400, 
            detail="Invalid location - coordinates outside service area. Only live GPS locations within India are accepted."
        )
    
    try:
        truck_location = TruckLocation(
            driver_id=current_user.id,
            latitude=location.latitude,
            longitude=location.longitude,
            accuracy=location.accuracy,
            speed=location.speed,
            heading=location.heading
        )
        db.add(truck_location)
        db.commit()
        db.refresh(truck_location)
        
        # Calculate time ago
        time_diff = datetime.utcnow() - truck_location.timestamp
        seconds = int(time_diff.total_seconds())
        if seconds < 60:
            time_ago = "just now"
        elif seconds < 3600:
            minutes = seconds // 60
            time_ago = f"{minutes} min ago"
        else:
            hours = seconds // 3600
            time_ago = f"{hours} hr ago"
        
        # Prepare response
        response = LocationResponse(
            id=truck_location.id,
            driver_id=current_user.id,
            driver_name=current_user.name,
            driver_mobile=current_user.mobile,
            latitude=truck_location.latitude,
            longitude=truck_location.longitude,
            accuracy=truck_location.accuracy,
            speed=truck_location.speed,
            heading=truck_location.heading,
            timestamp=truck_location.timestamp,
            time_ago=time_ago
        )
        
        # Broadcast to all connected WebSocket clients
        await manager.broadcast({
            "type": "location_update",
            "driver_id": current_user.id,
            "driver_name": current_user.name,
            "driver_mobile": current_user.mobile,
            "latitude": truck_location.latitude,
            "longitude": truck_location.longitude,
            "accuracy": truck_location.accuracy,
            "speed": truck_location.speed,
            "heading": truck_location.heading,
            "timestamp": truck_location.timestamp.isoformat(),
            "time_ago": time_ago
        })
        
        # Log activity
        DatabaseLogger.log_user_activity(
            user_id=current_user.id,
            action="location_update",
            description=f"GPS location updated: ({location.latitude}, {location.longitude})",
            db=db
        )
        
        return response
        
    except Exception as e:
        DatabaseLogger.log_error(
            error_type="LocationUpdateError",
            error_message=str(e),
            endpoint="/api/location/update",
            user_id=current_user.id,
            severity=LogLevel.ERROR,
            db=db
        )
        raise HTTPException(status_code=500, detail="Failed to update location")

@router.get("/driver/{driver_id}/latest", response_model=Optional[LocationResponse])
def get_latest_driver_location(
    driver_id: int,
    dest_lat: Optional[float] = Query(None, description="Destination latitude for distance/ETA calculation"),
    dest_long: Optional[float] = Query(None, description="Destination longitude for distance/ETA calculation"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the latest location of a specific driver
    Used by Admin dashboard and Customer tracking page
    Optional: Pass destination coordinates to get distance and ETA
    
    Authorization:
    - Admins can view any driver
    - Customers can only view drivers assigned to their orders
    - Drivers can view their own location
    """
    from models.user import UserRole
    from models.order import OrderStatus
    from models.customer import Customer
    
    # Admins can view any driver
    if current_user.role == UserRole.ADMIN:
        pass  # Authorized
    
    # Drivers can view their own location
    elif current_user.role == UserRole.DRIVER and current_user.id == driver_id:
        pass  # Authorized
    
    # Customers can only view drivers assigned to their active orders
    elif current_user.role == UserRole.CUSTOMER:
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        if not customer:
            raise HTTPException(status_code=403, detail="Customer profile not found")
        
        # Check if this driver is assigned to any of the customer's active orders
        active_order = db.query(Order).filter(
            Order.customer_id == customer.id,
            Order.driver_id == driver_id,
            Order.status.in_([OrderStatus.ASSIGNED, OrderStatus.IN_TRANSIT])
        ).first()
        
        if not active_order:
            raise HTTPException(
                status_code=403, 
                detail="You can only view location of drivers assigned to your active orders"
            )
    else:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get most recent location for this driver
    location = db.query(TruckLocation).filter(
        TruckLocation.driver_id == driver_id
    ).order_by(TruckLocation.timestamp.desc()).first()
    
    if not location:
        return None
    
    # Get driver info
    driver = db.query(User).filter(User.id == driver_id).first()
    if not driver:
        return None
    
    # Calculate time ago
    time_diff = datetime.utcnow() - location.timestamp
    seconds = int(time_diff.total_seconds())
    if seconds < 60:
        time_ago = "just now"
    elif seconds < 3600:
        minutes = seconds // 60
        time_ago = f"{minutes} min ago"
    else:
        hours = seconds // 3600
        time_ago = f"{hours} hr ago"
    
    # Calculate distance and ETA if destination provided
    distance_to_destination = None
    eta_minutes = None
    if dest_lat is not None and dest_long is not None:
        distance_to_destination = haversine_distance(
            location.latitude, location.longitude,
            dest_lat, dest_long
        )
        eta_minutes = calculate_eta(
            distance_to_destination, 
            location.speed
        )
    
    return LocationResponse(
        id=location.id,
        driver_id=driver.id,
        driver_name=driver.name,
        driver_mobile=driver.mobile,
        latitude=location.latitude,
        longitude=location.longitude,
        accuracy=location.accuracy,
        speed=location.speed,
        heading=location.heading,
        timestamp=location.timestamp,
        time_ago=time_ago,
        distance_to_destination=distance_to_destination,
        eta_minutes=eta_minutes
    )

@router.get("/all-active", response_model=List[LocationResponse])
def get_all_active_drivers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get latest locations of all active drivers (updated in last 30 minutes)
    Used by Admin dashboard for fleet tracking
    Includes current order info with customer delivery coordinates
    """
    thirty_mins_ago = datetime.utcnow() - timedelta(minutes=30)
    
    from sqlalchemy import func
    subquery = db.query(
        TruckLocation.driver_id,
        func.max(TruckLocation.timestamp).label('max_timestamp')
    ).filter(
        TruckLocation.timestamp >= thirty_mins_ago
    ).group_by(TruckLocation.driver_id).subquery()
    
    locations = db.query(TruckLocation).join(
        subquery,
        (TruckLocation.driver_id == subquery.c.driver_id) &
        (TruckLocation.timestamp == subquery.c.max_timestamp)
    ).all()
    
    results = []
    for location in locations:
        driver = db.query(User).filter(User.id == location.driver_id).first()
        if driver:
            time_diff = datetime.utcnow() - location.timestamp
            seconds = int(time_diff.total_seconds())
            if seconds < 60:
                time_ago = "just now"
            elif seconds < 3600:
                minutes = seconds // 60
                time_ago = f"{minutes} min ago"
            else:
                hours = seconds // 3600
                time_ago = f"{hours} hr ago"
            
            current_order_info = None
            active_order = db.query(Order).filter(
                Order.driver_id == driver.id,
                Order.status.in_([OrderStatus.ASSIGNED, OrderStatus.IN_TRANSIT])
            ).order_by(Order.updated_at.desc()).first()
            
            if active_order:
                customer = db.query(Customer).filter(Customer.id == active_order.customer_id).first()
                customer_name = customer.company_name if customer else "Customer"
                
                customer_lat = active_order.delivery_gps_lat
                customer_lng = active_order.delivery_gps_long
                
                if customer_lat is None and customer:
                    customer_lat = customer.latitude
                if customer_lng is None and customer:
                    customer_lng = customer.longitude
                
                current_order_info = CurrentOrderInfo(
                    id=active_order.id,
                    customer_name=customer_name,
                    customer_lat=customer_lat,
                    customer_lng=customer_lng,
                    liters=active_order.liters,
                    total_amount=active_order.amount,
                    delivery_address=active_order.delivery_address,
                    status=active_order.status.value if active_order.status else None
                )
            
            results.append(LocationResponse(
                id=location.id,
                driver_id=driver.id,
                driver_name=driver.name,
                driver_mobile=driver.mobile,
                driver_phone=driver.mobile,
                latitude=location.latitude,
                longitude=location.longitude,
                accuracy=location.accuracy,
                speed=location.speed,
                heading=location.heading,
                timestamp=location.timestamp,
                time_ago=time_ago,
                current_order=current_order_info
            ))
    
    return results

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """
    WebSocket endpoint for real-time location updates
    Requires authentication via token query parameter
    Only admins and customers with active orders can connect
    """
    from utils.auth import verify_token
    from models.user import UserRole
    
    # Verify authentication token
    try:
        payload = verify_token(token)
        if not payload or "user_id" not in payload:
            await websocket.close(code=1008, reason="Invalid authentication token")
            return
        
        # Only allow admins and customers to subscribe to location updates
        user_role = payload.get("role")
        if user_role not in [UserRole.ADMIN.value, UserRole.CUSTOMER.value]:
            await websocket.close(code=1008, reason="Unauthorized role")
            return
            
    except Exception as e:
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Echo back to confirm connection
            await websocket.send_json({"status": "connected"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
