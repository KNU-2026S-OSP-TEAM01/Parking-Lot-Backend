import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.models.parking_lot import ParkingLot

router = APIRouter()


class LotStatusResponse(BaseModel):
    lot_id: uuid.UUID
    name: str
    address: Optional[str]
    total_spaces: int
    available_spaces: int
    base_fee: int
    base_duration_minutes: int
    extra_fee_per_unit: int
    extra_fee_unit_minutes: int
    daily_max_fee: Optional[int]
    is_active: bool
    synced_at: datetime


@router.get("/status/{lot_id}", response_model=LotStatusResponse)
async def get_lot_status(
    lot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> LotStatusResponse:
    result = await db.execute(select(ParkingLot).where(ParkingLot.id == lot_id))
    lot = result.scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="lot_not_found")

    return LotStatusResponse(
        lot_id=lot.id,
        name=lot.name,
        address=lot.address,
        total_spaces=lot.total_spaces,
        available_spaces=lot.available_spaces,
        base_fee=lot.base_fee,
        base_duration_minutes=lot.base_duration_minutes,
        extra_fee_per_unit=lot.extra_fee_per_unit,
        extra_fee_unit_minutes=lot.extra_fee_unit_minutes,
        daily_max_fee=lot.daily_max_fee,
        is_active=lot.is_active,
        synced_at=datetime.now(timezone.utc),
    )
