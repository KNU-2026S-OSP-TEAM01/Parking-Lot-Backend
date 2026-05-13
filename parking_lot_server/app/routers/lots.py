import secrets
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.jwt_auth import get_current_user, get_owned_lot
from app.models.entry_exit_log import EntryExitLog
from app.models.parking_lot import ParkingLot
from app.models.vehicle import Vehicle
from app.schemas.log import LogOut
from app.schemas.lot import LotCreate, LotOut, LotPatch
from app.schemas.vehicle import VehicleOut
from app.services.crypto import aes_decrypt, aes_encrypt, hmac_hash
from app.services.fee import calculate_fee
from app.services.hub import notify_hub_lot_created, notify_hub_lot_deactivated

router = APIRouter()


def _mask_key(key: str) -> str:
    return key[:4] + "..." + key[-4:]


def _serialize_lot(lot: ParkingLot, *, mask_key: bool = True) -> LotOut:
    return LotOut(
        id=lot.id,
        owner_user_id=lot.owner_user_id,
        name=lot.name,
        address=lot.address,
        total_spaces=lot.total_spaces,
        available_spaces=lot.available_spaces,
        base_fee=lot.base_fee,
        base_duration_minutes=lot.base_duration_minutes,
        extra_fee_per_unit=lot.extra_fee_per_unit,
        extra_fee_unit_minutes=lot.extra_fee_unit_minutes,
        daily_max_fee=lot.daily_max_fee,
        api_key=_mask_key(lot.api_key) if mask_key else lot.api_key,
        is_active=lot.is_active,
        created_at=lot.created_at,
        updated_at=lot.updated_at,
    )


# ── 주차장 CRUD ───────────────────────────────────────────────────────────────

@router.post("/lots", response_model=LotOut, status_code=201)
async def create_lot(
    body: LotCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LotOut:
    lot = ParkingLot(
        **body.model_dump(),
        id=uuid.uuid4(),
        owner_user_id=uuid.UUID(current_user["sub"]),
        available_spaces=body.total_spaces,
        api_key=secrets.token_hex(32),
    )
    db.add(lot)
    await db.flush()
    await db.refresh(lot)

    if settings.mode == "public" and settings.hub_url:
        await notify_hub_lot_created(lot)

    return _serialize_lot(lot, mask_key=False)


@router.get("/lots", response_model=list[LotOut])
async def list_lots(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LotOut]:
    result = await db.execute(
        select(ParkingLot).where(ParkingLot.owner_user_id == uuid.UUID(current_user["sub"]))
    )
    return [_serialize_lot(lot) for lot in result.scalars().all()]


@router.get("/lots/{lot_id}", response_model=LotOut)
async def get_lot(
    lot_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LotOut:
    lot = await get_owned_lot(str(lot_id), current_user, db)
    return _serialize_lot(lot)


@router.patch("/lots/{lot_id}", response_model=LotOut)
async def update_lot(
    lot_id: uuid.UUID,
    body: LotPatch,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LotOut:
    lot = await get_owned_lot(str(lot_id), current_user, db)
    patch = body.model_dump(exclude_none=True)

    if "total_spaces" in patch:
        currently_parked = lot.total_spaces - lot.available_spaces
        new_total = patch["total_spaces"]
        if new_total < currently_parked:
            raise HTTPException(status_code=400, detail="invalid_total_spaces")
        # available_spaces를 새 total 기준으로 재계산
        patch["available_spaces"] = new_total - currently_parked

    for field, value in patch.items():
        setattr(lot, field, value)

    await db.flush()
    await db.refresh(lot)
    return _serialize_lot(lot)


@router.delete("/lots/{lot_id}", status_code=204)
async def delete_lot(
    lot_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    lot = await get_owned_lot(str(lot_id), current_user, db)

    if settings.mode == "public" and settings.hub_url:
        await notify_hub_lot_deactivated(lot_id)

    await db.delete(lot)
    await db.flush()


# ── 차량 현황 ─────────────────────────────────────────────────────────────────

@router.get("/lots/{lot_id}/vehicles", response_model=list[VehicleOut])
async def list_vehicles(
    lot_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[VehicleOut]:
    await get_owned_lot(str(lot_id), current_user, db)
    result = await db.execute(select(Vehicle).where(Vehicle.parking_lot_id == lot_id))
    return [
        VehicleOut(
            id=v.id,
            parking_lot_id=v.parking_lot_id,
            plate=aes_decrypt(v.plate_enc),
            entered_at=v.entered_at,
        )
        for v in result.scalars().all()
    ]


@router.delete("/lots/{lot_id}/vehicles/{vehicle_id}", status_code=204)
async def force_exit_vehicle(
    lot_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    lot = await get_owned_lot(str(lot_id), current_user, db)

    result = await db.execute(
        select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.parking_lot_id == lot_id)
    )
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="vehicle_not_found")

    now = datetime.now(timezone.utc)
    fee = calculate_fee(lot, vehicle.entered_at, now)

    db.add(EntryExitLog(
        parking_lot_id=lot.id,
        plate_hash=vehicle.plate_hash,
        plate_enc=vehicle.plate_enc,
        event_type="admin",
        fee=fee,
        client_timestamp=now,
        server_received_at=now,
    ))
    await db.delete(vehicle)
    lot.available_spaces += 1
    await db.flush()


# ── 입출차 로그 ───────────────────────────────────────────────────────────────

@router.get("/lots/{lot_id}/logs", response_model=list[LogOut])
async def list_logs(
    lot_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    date_from:   Optional[date] = Query(None),
    date_to:     Optional[date] = Query(None),
    plate:       Optional[str]  = Query(None),
    event_type:  Optional[str]  = Query(None),
    limit:       int            = Query(50, le=200),
    offset:      int            = Query(0, ge=0),
) -> list[LogOut]:
    await get_owned_lot(str(lot_id), current_user, db)

    query = (
        select(EntryExitLog)
        .where(EntryExitLog.parking_lot_id == lot_id)
        .order_by(EntryExitLog.client_timestamp.desc())
    )
    if date_from:
        query = query.where(EntryExitLog.client_timestamp >= date_from)
    if date_to:
        query = query.where(EntryExitLog.client_timestamp <= date_to)
    if plate:
        query = query.where(EntryExitLog.plate_hash == hmac_hash(plate))
    if event_type:
        query = query.where(EntryExitLog.event_type == event_type)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)

    return [
        LogOut(
            id=log.id,
            parking_lot_id=log.parking_lot_id,
            plate=aes_decrypt(log.plate_enc),
            event_type=log.event_type,
            fee=log.fee,
            client_timestamp=log.client_timestamp,
            server_received_at=log.server_received_at,
        )
        for log in result.scalars().all()
    ]
