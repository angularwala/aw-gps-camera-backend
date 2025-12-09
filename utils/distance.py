"""
Distance and ETA calculation utilities using Haversine formula and OSRM routing
"""
import math
import httpx
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

OSRM_BASE_URL = "https://router.project-osrm.org"

# Correction factors to align OSRM with Google Maps for Indian roads
# These values are tuned to approximate Google Maps results
# Distance: OSRM often underestimates due to missing local roads
DISTANCE_CORRECTION_FACTOR = 1.10

# Duration: OSRM assumes faster speeds than typical Indian traffic
# Single factor applied to all routes for consistency
DURATION_CORRECTION_FACTOR = 1.25

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth
    using the Haversine formula (straight-line distance)
    
    Args:
        lat1, lon1: First point coordinates (in degrees)
        lat2, lon2: Second point coordinates (in degrees)
    
    Returns:
        Distance in kilometers
    """
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    r = 6371
    
    return c * r

def get_road_distance(
    lat1: float, 
    lon1: float, 
    lat2: float, 
    lon2: float,
    timeout: float = 5.0
) -> Tuple[Optional[float], Optional[int]]:
    """
    Get actual road distance and duration using OSRM routing API.
    Falls back to Haversine distance if OSRM fails.
    
    Args:
        lat1, lon1: Origin coordinates (driver location)
        lat2, lon2: Destination coordinates (customer location)
        timeout: Request timeout in seconds
    
    Returns:
        Tuple of (distance_km, duration_minutes) or (None, None) on failure
    """
    try:
        url = f"{OSRM_BASE_URL}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
        params = {
            "overview": "false",
            "annotations": "false"
        }
        
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("code") == "Ok" and data.get("routes"):
                    route = data["routes"][0]
                    distance_meters = route.get("distance", 0)
                    duration_seconds = route.get("duration", 0)
                    
                    # Apply correction factors to match Google Maps
                    distance_km = (distance_meters / 1000) * DISTANCE_CORRECTION_FACTOR
                    duration_minutes = int((duration_seconds / 60) * DURATION_CORRECTION_FACTOR)
                    if duration_minutes == 0 and distance_km > 0.1:
                        duration_minutes = 1
                    
                    logger.debug(f"OSRM route (corrected): {distance_km:.2f} km, {duration_minutes} min")
                    return distance_km, duration_minutes
                else:
                    logger.warning(f"OSRM returned no routes: {data.get('code')}")
                    return None, None
            else:
                logger.warning(f"OSRM request failed with status {response.status_code}")
                return None, None
                
    except httpx.TimeoutException:
        logger.warning("OSRM request timed out")
        return None, None
    except Exception as e:
        logger.error(f"OSRM request error: {str(e)}")
        return None, None

def get_route_with_geometry(
    lat1: float, 
    lon1: float, 
    lat2: float, 
    lon2: float,
    timeout: float = 15.0
) -> Tuple[Optional[float], Optional[int], Optional[list]]:
    """
    Get road distance, duration, and route geometry using OSRM routing API.
    Returns geometry as list of [longitude, latitude] coordinates for map display.
    
    Args:
        lat1, lon1: Origin coordinates (driver location)
        lat2, lon2: Destination coordinates (customer location)
        timeout: Request timeout in seconds (increased for long routes)
    
    Returns:
        Tuple of (distance_km, duration_minutes, geometry_coords) or (None, None, None) on failure
        geometry_coords is a list of [lng, lat] pairs
    """
    try:
        url = f"{OSRM_BASE_URL}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
        params = {
            "overview": "simplified",
            "geometries": "geojson"
        }
        
        logger.info(f"OSRM geometry request: {url}")
        
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params=params)
            
            logger.info(f"OSRM response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("code") == "Ok" and data.get("routes"):
                    route = data["routes"][0]
                    distance_meters = route.get("distance", 0)
                    duration_seconds = route.get("duration", 0)
                    geometry = route.get("geometry", {})
                    coordinates = geometry.get("coordinates", [])
                    
                    distance_km = (distance_meters / 1000) * DISTANCE_CORRECTION_FACTOR
                    duration_minutes = int((duration_seconds / 60) * DURATION_CORRECTION_FACTOR)
                    if duration_minutes == 0 and distance_km > 0.1:
                        duration_minutes = 1
                    
                    logger.info(f"OSRM route with geometry (corrected): {distance_km:.2f} km, {duration_minutes} min, {len(coordinates)} points")
                    return distance_km, duration_minutes, coordinates
                else:
                    logger.warning(f"OSRM returned no routes: {data.get('code')}")
                    return None, None, None
            else:
                logger.warning(f"OSRM request failed with status {response.status_code}")
                return None, None, None
                
    except httpx.TimeoutException:
        logger.warning(f"OSRM request timed out for geometry (timeout={timeout}s)")
        return None, None, None
    except Exception as e:
        logger.error(f"OSRM request error for geometry: {str(e)}")
        return None, None, None

def get_distance_and_eta(
    driver_lat: float,
    driver_lon: float,
    customer_lat: float,
    customer_lon: float,
    current_speed_kmh: Optional[float] = None,
    use_road_distance: bool = True
) -> Tuple[float, int, bool]:
    """
    Get distance and ETA between driver and customer locations.
    Uses OSRM for road distance by default, falls back to Haversine.
    
    Args:
        driver_lat, driver_lon: Driver's current GPS coordinates
        customer_lat, customer_lon: Customer's delivery coordinates
        current_speed_kmh: Current driving speed (used for Haversine ETA fallback)
        use_road_distance: Whether to try OSRM first (default: True)
    
    Returns:
        Tuple of (distance_km, eta_minutes, is_road_distance)
        is_road_distance indicates if actual road distance was used
    """
    if use_road_distance:
        road_distance, road_eta = get_road_distance(
            driver_lat, driver_lon,
            customer_lat, customer_lon
        )
        
        if road_distance is not None and road_eta is not None:
            return road_distance, road_eta, True
    
    straight_distance = haversine_distance(
        driver_lat, driver_lon,
        customer_lat, customer_lon
    )
    eta = calculate_eta(straight_distance, current_speed_kmh)
    
    return straight_distance, eta, False

def calculate_eta(distance_km: float, current_speed_kmh: Optional[float] = None, avg_speed_kmh: float = 40.0) -> int:
    """
    Calculate estimated time of arrival in minutes
    
    Args:
        distance_km: Distance to destination in kilometers
        current_speed_kmh: Current speed in km/h (if available)
        avg_speed_kmh: Average speed to use if current speed is not available or too low (default: 40 km/h)
    
    Returns:
        ETA in minutes
    """
    speed_to_use = current_speed_kmh if (current_speed_kmh and current_speed_kmh > 5) else avg_speed_kmh
    
    time_hours = distance_km / speed_to_use
    time_minutes = int(time_hours * 60)
    
    return time_minutes

def format_distance(distance_km: float) -> str:
    """
    Format distance for display
    
    Args:
        distance_km: Distance in kilometers
    
    Returns:
        Formatted distance string
    """
    if distance_km < 1:
        return f"{int(distance_km * 1000)} m"
    else:
        return f"{distance_km:.2f} km"

def format_eta(eta_minutes: int) -> str:
    """
    Format ETA for display
    
    Args:
        eta_minutes: ETA in minutes
    
    Returns:
        Formatted ETA string
    """
    if eta_minutes < 60:
        return f"{eta_minutes} min"
    else:
        hours = eta_minutes // 60
        minutes = eta_minutes % 60
        if minutes == 0:
            return f"{hours} hr"
        else:
            return f"{hours} hr {minutes} min"

def get_alternative_routes(
    lat1: float, 
    lon1: float, 
    lat2: float, 
    lon2: float,
    timeout: float = 5.0
) -> list:
    """
    Get multiple alternative routes from OSRM routing API.
    Returns up to 3 route options for driver to choose from.
    
    Args:
        lat1, lon1: Origin coordinates (driver location)
        lat2, lon2: Destination coordinates (customer location)
        timeout: Request timeout in seconds
    
    Returns:
        List of route dictionaries with distance_km, duration_minutes, and coordinates
    """
    try:
        url = f"{OSRM_BASE_URL}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "alternatives": "true"
        }
        
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("code") == "Ok" and data.get("routes"):
                    routes = []
                    for idx, route in enumerate(data["routes"][:3]):
                        distance_meters = route.get("distance", 0)
                        duration_seconds = route.get("duration", 0)
                        geometry = route.get("geometry", {})
                        coordinates = geometry.get("coordinates", [])
                        
                        # Apply correction factors to match Google Maps
                        distance_km = (distance_meters / 1000) * DISTANCE_CORRECTION_FACTOR
                        duration_minutes = int((duration_seconds / 60) * DURATION_CORRECTION_FACTOR)
                        if duration_minutes == 0 and distance_km > 0.1:
                            duration_minutes = 1
                        
                        routes.append({
                            "route_index": idx,
                            "distance_km": round(distance_km, 2),
                            "duration_minutes": duration_minutes,
                            "coordinates": coordinates
                        })
                    
                    logger.debug(f"OSRM returned {len(routes)} alternative routes")
                    return routes
                else:
                    logger.warning(f"OSRM returned no routes: {data.get('code')}")
                    return []
            else:
                logger.warning(f"OSRM alternatives request failed with status {response.status_code}")
                return []
                
    except httpx.TimeoutException:
        logger.warning("OSRM alternatives request timed out")
        return []
    except Exception as e:
        logger.error(f"OSRM alternatives request error: {str(e)}")
        return []

def point_to_line_distance(point_lat: float, point_lng: float, line_coords: list) -> float:
    """
    Calculate minimum distance from a point to a polyline in meters.
    Used to detect if driver has deviated from selected route.
    
    Args:
        point_lat, point_lng: Point coordinates (driver location)
        line_coords: List of [lng, lat] coordinates forming the route line
    
    Returns:
        Minimum distance in meters from point to any segment of the line
    """
    if not line_coords or len(line_coords) < 2:
        return float('inf')
    
    min_distance = float('inf')
    
    for i in range(len(line_coords) - 1):
        seg_start = line_coords[i]
        seg_end = line_coords[i + 1]
        
        dist = point_to_segment_distance(
            point_lat, point_lng,
            seg_start[1], seg_start[0],
            seg_end[1], seg_end[0]
        )
        min_distance = min(min_distance, dist)
    
    return min_distance

def point_to_segment_distance(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float
) -> float:
    """
    Calculate distance from point P to line segment AB in meters.
    Uses projection to find closest point on segment.
    """
    dx = bx - ax
    dy = by - ay
    
    if dx == 0 and dy == 0:
        return haversine_distance(px, py, ax, ay) * 1000
    
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    
    closest_x = ax + t * dx
    closest_y = ay + t * dy
    
    return haversine_distance(px, py, closest_x, closest_y) * 1000
