import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.jwt_auth import get_current_user
from app.models.entry_exit_log import EntryExitLog
from app.models.parking_lot import ParkingLot
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleOut
from app.services.crypto import aes_decrypt
from app.services.fee import calculate_fee

router = APIRouter()


@router.get("/vehicles", response_model=list[VehicleOut])
async def list_vehicles(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[VehicleOut]:
    query = select(Vehicle)
    if user["role"] == "admin":
        query = query.where(Vehicle.parking_lot_id == user["lot_id"])
    result = await db.execute(query)
    return [
        VehicleOut(
            id=v.id,
            parking_lot_id=v.parking_lot_id,
            plate=aes_decrypt(v.plate_enc),
            entered_at=v.entered_at,
        )
        for v in result.scalars().all()
    ]


@router.delete("/vehicles/{vehicle_id}", status_code=204)
async def force_exit_vehicle(
    vehicle_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="vehicle_not_found")

    if user["role"] == "admin" and str(vehicle.parking_lot_id) != user["lot_id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    lot_result = await db.execute(
        select(ParkingLot).where(ParkingLot.id == vehicle.parking_lot_id)
    )
    lot = lot_result.scalar_one()

    now = datetime.now(timezone.utc)
    plate_enc  = vehicle.plate_enc
    plate_hash = vehicle.plate_hash
    entered_at = vehicle.entered_at
    fee = calculate_fee(lot, entered_at, now)

    await db.delete(vehicle)
    lot.available_spaces += 1
    db.add(EntryExitLog(
        parking_lot_id=lot.id,
        plate_hash=plate_hash,
        plate_enc=plate_enc,
        event_type="admin",
        fee=fee,
        client_timestamp=now,
        server_received_at=now,
    ))
    await db.flush()
