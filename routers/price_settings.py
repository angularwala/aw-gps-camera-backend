from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal

from database import get_db
from models import User, PriceSettings
from utils.auth_dependency import get_current_user, get_current_admin
from routers.tracking import manager

router = APIRouter(prefix="/api/price-settings", tags=["price-settings"])


class PriceSettingsResponse(BaseModel):
    id: int
    current_rate: float
    effective_at: datetime
    updated_at: datetime
    updated_by: Optional[int]
    rate_version: int
    
    class Config:
        from_attributes = True


class UpdatePriceRequest(BaseModel):
    current_rate: float


@router.get("/", response_model=PriceSettingsResponse)
def get_price_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current diesel price settings.
    Available to all authenticated users.
    """
    settings = db.query(PriceSettings).first()
    
    if not settings:
        settings = PriceSettings(
            current_rate=Decimal("91.55"),
            effective_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return PriceSettingsResponse(
        id=settings.id,
        current_rate=float(settings.current_rate),
        effective_at=settings.effective_at,
        updated_at=settings.updated_at,
        updated_by=settings.updated_by,
        rate_version=int(settings.updated_at.timestamp())
    )


@router.put("/", response_model=PriceSettingsResponse)
async def update_price_settings(
    request: UpdatePriceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Update diesel price settings.
    Admin only.
    """
    if request.current_rate <= 0:
        raise HTTPException(status_code=400, detail="Rate must be greater than 0")
    
    settings = db.query(PriceSettings).first()
    
    if not settings:
        settings = PriceSettings(
            current_rate=Decimal(str(request.current_rate)),
            effective_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            updated_by=current_user.id
        )
        db.add(settings)
    else:
        settings.current_rate = Decimal(str(request.current_rate))
        settings.effective_at = datetime.utcnow()
        settings.updated_at = datetime.utcnow()
        settings.updated_by = current_user.id
    
    db.commit()
    db.refresh(settings)
    
    rate_version = int(settings.updated_at.timestamp())
    
    await manager.broadcast({
        "type": "rate_updated",
        "data": {
            "current_rate": float(settings.current_rate),
            "rate_version": rate_version,
            "updated_at": settings.updated_at.isoformat(),
            "updated_by": current_user.name
        }
    })
    
    return PriceSettingsResponse(
        id=settings.id,
        current_rate=float(settings.current_rate),
        effective_at=settings.effective_at,
        updated_at=settings.updated_at,
        updated_by=settings.updated_by,
        rate_version=rate_version
    )
