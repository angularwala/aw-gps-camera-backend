"""
Analytics endpoints for tracking km traveled, fuel consumption, and other metrics
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta, date
from database import get_db
from models.truck_location import TruckLocation
from models.user import User
from utils.auth_dependency import get_current_admin
from utils.distance import haversine_distance

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

class SimpleKmResponse(BaseModel):
    total_km: float = 0.0
    total_deliveries: int = 0
    drivers: list = []

@router.get("/km", response_model=SimpleKmResponse)
def get_km_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get simple KM analytics summary"""
    from models.user import UserRole
    
    drivers = db.query(User).filter(User.role == UserRole.DRIVER).all()
    driver_list = [{"id": d.id, "name": d.name, "km": 0.0} for d in drivers]
    
    return SimpleKmResponse(
        total_km=0.0,
        total_deliveries=0,
        drivers=driver_list
    )

class DriverTravelStats(BaseModel):
    driver_id: int
    driver_name: str
    total_km: float
    trip_count: int
    avg_speed: Optional[float]

class TravelAnalytics(BaseModel):
    period: str  # 'daily', 'weekly', 'monthly', 'yearly'
    start_date: date
    end_date: date
    total_km: float
    by_driver: List[DriverTravelStats]

def calculate_distance_traveled(locations: List[TruckLocation]) -> float:
    """Calculate total distance traveled from a list of location points"""
    if len(locations) < 2:
        return 0.0
    
    total_distance = 0.0
    for i in range(len(locations) - 1):
        distance = haversine_distance(
            locations[i].latitude, locations[i].longitude,
            locations[i + 1].latitude, locations[i + 1].longitude
        )
        # Only add if distance is reasonable (< 5km between points)
        # This filters out GPS errors
        if distance < 5.0:
            total_distance += distance
    
    return total_distance

@router.get("/km-traveled/daily", response_model=TravelAnalytics)
def get_daily_km_traveled(
    target_date: Optional[date] = Query(None, description="Target date (defaults to today)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get km traveled by all drivers for a specific day"""
    if target_date is None:
        target_date = date.today()
    
    start_datetime = datetime.combine(target_date, datetime.min.time())
    end_datetime = datetime.combine(target_date, datetime.max.time())
    
    # Get all locations for the day
    locations = db.query(TruckLocation).filter(
        and_(
            TruckLocation.timestamp >= start_datetime,
            TruckLocation.timestamp <= end_datetime
        )
    ).order_by(TruckLocation.driver_id, TruckLocation.timestamp).all()
    
    # Group by driver
    driver_stats = {}
    total_km = 0.0
    
    for driver_id in set(loc.driver_id for loc in locations):
        driver_locations = [loc for loc in locations if loc.driver_id == driver_id]
        driver = db.query(User).filter(User.id == driver_id).first()
        
        if driver:
            km_traveled = calculate_distance_traveled(driver_locations)
            avg_speed = sum(loc.speed for loc in driver_locations if loc.speed) / len(driver_locations) if driver_locations else 0
            
            driver_stats[driver_id] = DriverTravelStats(
                driver_id=driver.id,
                driver_name=driver.name,
                total_km=round(km_traveled, 2),
                trip_count=len(driver_locations),
                avg_speed=round(avg_speed, 2) if avg_speed else None
            )
            total_km += km_traveled
    
    return TravelAnalytics(
        period="daily",
        start_date=target_date,
        end_date=target_date,
        total_km=round(total_km, 2),
        by_driver=list(driver_stats.values())
    )

@router.get("/km-traveled/weekly", response_model=TravelAnalytics)
def get_weekly_km_traveled(
    target_date: Optional[date] = Query(None, description="Any date in the target week (defaults to current week)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get km traveled by all drivers for a specific week"""
    if target_date is None:
        target_date = date.today()
    
    # Calculate start and end of week (Monday to Sunday)
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    start_datetime = datetime.combine(start_of_week, datetime.min.time())
    end_datetime = datetime.combine(end_of_week, datetime.max.time())
    
    # Get all locations for the week
    locations = db.query(TruckLocation).filter(
        and_(
            TruckLocation.timestamp >= start_datetime,
            TruckLocation.timestamp <= end_datetime
        )
    ).order_by(TruckLocation.driver_id, TruckLocation.timestamp).all()
    
    # Group by driver
    driver_stats = {}
    total_km = 0.0
    
    for driver_id in set(loc.driver_id for loc in locations):
        driver_locations = [loc for loc in locations if loc.driver_id == driver_id]
        driver = db.query(User).filter(User.id == driver_id).first()
        
        if driver:
            km_traveled = calculate_distance_traveled(driver_locations)
            avg_speed = sum(loc.speed for loc in driver_locations if loc.speed) / len(driver_locations) if driver_locations else 0
            
            driver_stats[driver_id] = DriverTravelStats(
                driver_id=driver.id,
                driver_name=driver.name,
                total_km=round(km_traveled, 2),
                trip_count=len(driver_locations),
                avg_speed=round(avg_speed, 2) if avg_speed else None
            )
            total_km += km_traveled
    
    return TravelAnalytics(
        period="weekly",
        start_date=start_of_week,
        end_date=end_of_week,
        total_km=round(total_km, 2),
        by_driver=list(driver_stats.values())
    )

@router.get("/km-traveled/monthly", response_model=TravelAnalytics)
def get_monthly_km_traveled(
    year: Optional[int] = Query(None, description="Year (defaults to current year)"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month 1-12 (defaults to current month)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get km traveled by all drivers for a specific month"""
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year, 12, 31)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Get all locations for the month
    locations = db.query(TruckLocation).filter(
        and_(
            TruckLocation.timestamp >= start_datetime,
            TruckLocation.timestamp <= end_datetime
        )
    ).order_by(TruckLocation.driver_id, TruckLocation.timestamp).all()
    
    # Group by driver
    driver_stats = {}
    total_km = 0.0
    
    for driver_id in set(loc.driver_id for loc in locations):
        driver_locations = [loc for loc in locations if loc.driver_id == driver_id]
        driver = db.query(User).filter(User.id == driver_id).first()
        
        if driver:
            km_traveled = calculate_distance_traveled(driver_locations)
            avg_speed = sum(loc.speed for loc in driver_locations if loc.speed) / len(driver_locations) if driver_locations else 0
            
            driver_stats[driver_id] = DriverTravelStats(
                driver_id=driver.id,
                driver_name=driver.name,
                total_km=round(km_traveled, 2),
                trip_count=len(driver_locations),
                avg_speed=round(avg_speed, 2) if avg_speed else None
            )
            total_km += km_traveled
    
    return TravelAnalytics(
        period="monthly",
        start_date=start_date,
        end_date=end_date,
        total_km=round(total_km, 2),
        by_driver=list(driver_stats.values())
    )

@router.get("/km-traveled/yearly", response_model=TravelAnalytics)
def get_yearly_km_traveled(
    year: Optional[int] = Query(None, description="Year (defaults to current year)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get km traveled by all drivers for a specific year"""
    if year is None:
        year = date.today().year
    
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Get all locations for the year
    locations = db.query(TruckLocation).filter(
        and_(
            TruckLocation.timestamp >= start_datetime,
            TruckLocation.timestamp <= end_datetime
        )
    ).order_by(TruckLocation.driver_id, TruckLocation.timestamp).all()
    
    # Group by driver
    driver_stats = {}
    total_km = 0.0
    
    for driver_id in set(loc.driver_id for loc in locations):
        driver_locations = [loc for loc in locations if loc.driver_id == driver_id]
        driver = db.query(User).filter(User.id == driver_id).first()
        
        if driver:
            km_traveled = calculate_distance_traveled(driver_locations)
            avg_speed = sum(loc.speed for loc in driver_locations if loc.speed) / len(driver_locations) if driver_locations else 0
            
            driver_stats[driver_id] = DriverTravelStats(
                driver_id=driver.id,
                driver_name=driver.name,
                total_km=round(km_traveled, 2),
                trip_count=len(driver_locations),
                avg_speed=round(avg_speed, 2) if avg_speed else None
            )
            total_km += km_traveled
    
    return TravelAnalytics(
        period="yearly",
        start_date=start_date,
        end_date=end_date,
        total_km=round(total_km, 2),
        by_driver=list(driver_stats.values())
    )
