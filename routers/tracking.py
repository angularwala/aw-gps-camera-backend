from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Tuple
from datetime import datetime
from database import get_db
from models.truck_location import TruckLocation
from models.user import User
from models.order import Order, OrderStatus
from models.customer import Customer
from utils.auth_dependency import get_current_user, get_current_admin_or_driver
from utils.distance import get_distance_and_eta, get_route_with_geometry, haversine_distance, get_alternative_routes
import json
import math
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tracking", tags=["Tracking"])

route_cache: Dict[int, Tuple[float, float, float, float, List[List[float]]]] = {}
selected_route_cache: Dict[int, int] = {}
ROUTE_CACHE_THRESHOLD_METERS = 100
OFF_ROUTE_THRESHOLD_METERS = 50

def is_valid_india_location(latitude: float, longitude: float) -> bool:
    """
    Validates that coordinates are within India's geographic boundaries.
    Rejects test/dummy locations from outside service area.
    India bounds: Lat 6.5 to 35.5, Long 68 to 97.5
    """
    return 6.5 <= latitude <= 35.5 and 68.0 <= longitude <= 97.5

class LocationUpdate(BaseModel):
    driver_id: int
    latitude: float
    longitude: float

class LocationResponse(BaseModel):
    id: int
    driver_id: int
    latitude: float
    longitude: float
    timestamp: datetime
    
    class Config:
        from_attributes = True

class RouteOption(BaseModel):
    route_index: int
    distance_km: float
    duration_minutes: int
    coordinates: List[List[float]]

class OrderTrackingResponse(BaseModel):
    order_id: int
    driver_id: int
    driver_name: str
    driver_mobile: Optional[str] = None
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    timestamp: datetime
    customer_lat: Optional[float] = None
    customer_lng: Optional[float] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    distance_km: Optional[float] = None
    eta_minutes: Optional[int] = None
    route_geometry: Optional[List[List[float]]] = None
    selected_route_index: Optional[int] = None
    
    class Config:
        from_attributes = True

class AlternativeRoutesResponse(BaseModel):
    order_id: int
    routes: List[RouteOption]
    selected_route_index: int

class SelectRouteRequest(BaseModel):
    route_index: int

class RecalculateRouteRequest(BaseModel):
    driver_lat: float
    driver_lng: float

@router.get("/{order_id}", response_model=OrderTrackingResponse)
def get_order_tracking(
    order_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Get real-time tracking data for a specific order.
    Returns the driver's current location and customer delivery coordinates.
    Used by admin live tracking and customer tracking screens.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if not order.driver_id:
        raise HTTPException(status_code=404, detail="No driver assigned to this order")
    
    if order.status not in [OrderStatus.ASSIGNED, OrderStatus.IN_TRANSIT]:
        raise HTTPException(status_code=404, detail="Order is not in trackable status")
    
    location = db.query(TruckLocation).filter(
        TruckLocation.driver_id == order.driver_id
    ).order_by(TruckLocation.timestamp.desc()).first()
    
    if not location:
        raise HTTPException(status_code=404, detail="No location data found for driver")
    
    driver = db.query(User).filter(User.id == order.driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
    
    customer_lat = None
    customer_lng = None
    customer_name = None
    customer_address = None
    
    if order.delivery_gps_lat and order.delivery_gps_long:
        customer_lat = order.delivery_gps_lat
        customer_lng = order.delivery_gps_long
    elif customer:
        customer_lat = customer.gps_lat
        customer_lng = customer.gps_long
    
    if customer:
        customer_name = customer.company_name
        customer_address = order.delivery_address or customer.address
    
    distance_km = None
    eta_minutes = None
    route_geometry = None
    
    driver_lat = float(location.latitude)
    driver_lng = float(location.longitude)
    cust_lat = float(customer_lat) if customer_lat else None
    cust_lng = float(customer_lng) if customer_lng else None
    
    if cust_lat and cust_lng:
        logger.info(f"Order {order_id}: Fetching route from driver ({driver_lat}, {driver_lng}) to customer ({cust_lat}, {cust_lng})")
        cached = route_cache.get(order_id)
        should_refetch = True
        
        if cached:
            cached_driver_lat, cached_driver_lng, cached_cust_lat, cached_cust_lng, cached_route = cached
            movement_km = haversine_distance(cached_driver_lat, cached_driver_lng, driver_lat, driver_lng)
            movement_meters = movement_km * 1000
            
            if movement_meters < ROUTE_CACHE_THRESHOLD_METERS:
                should_refetch = False
                route_geometry = cached_route
                logger.info(f"Order {order_id}: Using cached route with {len(cached_route) if cached_route else 0} points (driver moved {movement_meters:.0f}m)")
        
        if should_refetch:
            logger.info(f"Order {order_id}: Fetching new route from OSRM...")
            road_distance, road_eta, route_coords = get_route_with_geometry(
                driver_lat, driver_lng,
                cust_lat, cust_lng,
                timeout=20.0
            )
            
            logger.info(f"Order {order_id}: OSRM result - distance: {road_distance}, eta: {road_eta}, coords: {len(route_coords) if route_coords else 0}")
            
            if road_distance is not None and road_eta is not None:
                distance_km = road_distance
                eta_minutes = road_eta
                if route_coords:
                    route_geometry = route_coords
                    route_cache[order_id] = (driver_lat, driver_lng, cust_lat, cust_lng, route_coords)
                    logger.info(f"Order {order_id}: Cached new route with {len(route_coords)} points")
            
            if route_geometry is None and cached:
                route_geometry = cached[4]
                logger.info(f"Order {order_id}: Using cached route geometry ({len(cached[4]) if cached[4] else 0} points)")
        
        if distance_km is None:
            logger.info(f"Order {order_id}: Using fallback distance calculation")
            distance_km, eta_minutes, is_road = get_distance_and_eta(
                driver_lat, driver_lng,
                cust_lat, cust_lng,
                current_speed_kmh=float(location.speed) if location.speed else None
            )
        
        if route_geometry is None and distance_km is not None:
            logger.info(f"Order {order_id}: Attempting to fetch route geometry separately...")
            _, _, route_coords = get_route_with_geometry(
                driver_lat, driver_lng,
                cust_lat, cust_lng,
                timeout=25.0
            )
            if route_coords:
                route_geometry = route_coords
                route_cache[order_id] = (driver_lat, driver_lng, cust_lat, cust_lng, route_coords)
                logger.info(f"Order {order_id}: Got route geometry on second attempt: {len(route_coords)} points")
        
        logger.info(f"Order {order_id}: Final response - distance: {distance_km}, eta: {eta_minutes}, route_points: {len(route_geometry) if route_geometry else 0}")
    
    return OrderTrackingResponse(
        order_id=order.id,
        driver_id=driver.id,
        driver_name=driver.name,
        driver_mobile=driver.mobile,
        latitude=location.latitude,
        longitude=location.longitude,
        accuracy=location.accuracy,
        speed=location.speed,
        heading=location.heading,
        timestamp=location.timestamp,
        customer_lat=customer_lat,
        customer_lng=customer_lng,
        customer_name=customer_name,
        customer_address=customer_address,
        distance_km=round(distance_km, 2) if distance_km else None,
        eta_minutes=eta_minutes,
        route_geometry=route_geometry,
        selected_route_index=selected_route_cache.get(order_id, 0)
    )

@router.get("/{order_id}/routes", response_model=AlternativeRoutesResponse)
def get_alternative_routes_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get alternative route options for an order.
    Returns up to 3 routes that driver can choose from.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if not order.driver_id:
        raise HTTPException(status_code=404, detail="No driver assigned to this order")
    
    location = db.query(TruckLocation).filter(
        TruckLocation.driver_id == order.driver_id
    ).order_by(TruckLocation.timestamp.desc()).first()
    
    if not location:
        raise HTTPException(status_code=404, detail="No location data found for driver")
    
    customer_lat = order.delivery_gps_lat
    customer_lng = order.delivery_gps_long
    
    if not customer_lat or not customer_lng:
        customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
        if customer:
            customer_lat = customer.gps_lat
            customer_lng = customer.gps_long
    
    if not customer_lat or not customer_lng:
        raise HTTPException(status_code=404, detail="Customer location not available")
    
    routes = get_alternative_routes(
        float(location.latitude), float(location.longitude),
        float(customer_lat), float(customer_lng)
    )
    
    if not routes:
        raise HTTPException(status_code=404, detail="Could not calculate routes")
    
    route_options = [RouteOption(**r) for r in routes]
    selected_index = selected_route_cache.get(order_id, 0)
    
    return AlternativeRoutesResponse(
        order_id=order_id,
        routes=route_options,
        selected_route_index=selected_index
    )

@router.post("/{order_id}/select-route")
def select_route(
    order_id: int,
    request: SelectRouteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_driver)
):
    """
    Driver selects which route to use.
    Clears the route cache to force refetch with selected route.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if current_user.role == "driver" and order.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this order's route")
    
    selected_route_cache[order_id] = request.route_index
    
    if order_id in route_cache:
        del route_cache[order_id]
    
    logger.info(f"Order {order_id}: Driver selected route index {request.route_index}")
    
    return {"success": True, "selected_route_index": request.route_index}

@router.post("/{order_id}/recalculate")
def recalculate_route(
    order_id: int,
    request: RecalculateRouteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_driver)
):
    """
    Recalculate route from driver's current position.
    Called when driver deviates from selected route.
    Returns new route options.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if current_user.role == "driver" and order.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this order's route")
    
    customer_lat = order.delivery_gps_lat
    customer_lng = order.delivery_gps_long
    
    if not customer_lat or not customer_lng:
        customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
        if customer:
            customer_lat = customer.gps_lat
            customer_lng = customer.gps_long
    
    if not customer_lat or not customer_lng:
        raise HTTPException(status_code=404, detail="Customer location not available")
    
    if order_id in route_cache:
        del route_cache[order_id]
    
    selected_route_cache[order_id] = 0
    
    routes = get_alternative_routes(
        request.driver_lat, request.driver_lng,
        float(customer_lat), float(customer_lng)
    )
    
    if not routes:
        road_distance, road_eta, route_coords = get_route_with_geometry(
            request.driver_lat, request.driver_lng,
            float(customer_lat), float(customer_lng)
        )
        
        if route_coords:
            routes = [{
                "route_index": 0,
                "distance_km": round(road_distance, 2) if road_distance else 0,
                "duration_minutes": road_eta if road_eta else 0,
                "coordinates": route_coords
            }]
    
    if not routes:
        raise HTTPException(status_code=404, detail="Could not calculate new routes")
    
    route_cache[order_id] = (
        request.driver_lat, request.driver_lng,
        float(customer_lat), float(customer_lng),
        routes[0]["coordinates"]
    )
    
    logger.info(f"Order {order_id}: Route recalculated from driver position, {len(routes)} options")
    
    route_options = [RouteOption(**r) for r in routes]
    
    return {
        "success": True,
        "routes": [r.dict() for r in route_options],
        "selected_route_index": 0
    }

# Store active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@router.post("/update", response_model=LocationResponse)
def update_location(request: LocationUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_or_driver)):
    """
    Legacy endpoint - prefer using /api/location/update instead.
    Only accepts live GPS coordinates from driver devices.
    """
    if not is_valid_india_location(request.latitude, request.longitude):
        raise HTTPException(status_code=400, detail="Invalid location - coordinates outside service area")
    
    location = TruckLocation(
        driver_id=request.driver_id,
        latitude=request.latitude,
        longitude=request.longitude
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    
    return location

@router.get("/truck/{driver_id}", response_model=LocationResponse)
@router.get("/driver/{driver_id}", response_model=LocationResponse)
def get_driver_location(driver_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    location = db.query(TruckLocation).filter(
        TruckLocation.driver_id == driver_id
    ).order_by(TruckLocation.timestamp.desc()).first()
    
    if not location:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No location data found for driver")
    
    return location

@router.websocket("/ws/{driver_id}")
async def websocket_endpoint(websocket: WebSocket, driver_id: int):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            location_data = json.loads(data)
            
            latitude = location_data.get('latitude') or location_data.get('lat')
            longitude = location_data.get('longitude') or location_data.get('long')
            
            if not latitude or not longitude:
                continue
                
            if not is_valid_india_location(latitude, longitude):
                continue
            
            db = next(get_db())
            location = TruckLocation(
                driver_id=driver_id,
                latitude=latitude,
                longitude=longitude
            )
            db.add(location)
            db.commit()
            db.close()
            
            await manager.broadcast({
                "driver_id": driver_id,
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": datetime.utcnow().isoformat()
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
