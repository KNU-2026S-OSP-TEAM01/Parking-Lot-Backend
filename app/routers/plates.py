import math
import uuid
from datetime import datetime, timezone
from typing import Union

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.api_key import get_parking_lot
from app.models.entry_exit_log import EntryExitLog
from app.models.parking_lot import ParkingLot
from app.models.vehicle import Vehicle
from app.schemas.plate import EntryResponse, ExitResponse, PlateRequest
from app.services.crypto import aes_encrypt, hmac_hash
from app.services.fee import calculate_fee

router = APIRouter()


@router.post("/plates")
async def process_plate(
    body: PlateRequest,
    lot: ParkingLot = Depends(get_parking_lot),
    db: AsyncSession = Depends(get_db),
) -> Union[EntryResponse, ExitResponse]:
    plate_hash = hmac_hash(body.plate)
    client_ts = body.timestamp

    result = await db.execute(
        select(Vehicle).where(
            Vehicle.parking_lot_id == lot.id,
            Vehicle.plate_hash == plate_hash,
        )
    )
    vehicle = result.scalar_one_or_none()

    if vehicle is None:
        # 입차
        if lot.available_spaces <= 0:
            raise HTTPException(status_code=409, detail="parking_lot_full")

        plate_enc = aes_encrypt(body.plate)
        db.add(Vehicle(
            id=uuid.uuid4(),
            parking_lot_id=lot.id,
            plate_hash=plate_hash,
            plate_enc=plate_enc,
            entered_at=client_ts,
        ))
        lot.available_spaces -= 1
        db.add(EntryExitLog(
            id=uuid.uuid4(),
            parking_lot_id=lot.id,
            plate_hash=plate_hash,
            plate_enc=plate_enc,
            event_type="entry",
            fee=None,
            client_timestamp=client_ts,
            server_received_at=datetime.now(timezone.utc),
        ))
        return EntryResponse(event="entry", entered_at=client_ts)

    else:
        # 출차: plate_enc, entered_at을 DELETE 이전에 반드시 읽어야 함
        plate_enc  = vehicle.plate_enc
        entered_at = vehicle.entered_at
        fee = calculate_fee(lot, entered_at, client_ts)
        parked_duration_minutes = math.ceil(
            (client_ts - entered_at).total_seconds() / 60
        )

        await db.delete(vehicle)
        lot.available_spaces += 1
        db.add(EntryExitLog(
            id=uuid.uuid4(),
            parking_lot_id=lot.id,
            plate_hash=plate_hash,
            plate_enc=plate_enc,
            event_type="exit",
            fee=fee,
            client_timestamp=client_ts,
            server_received_at=datetime.now(timezone.utc),
        ))
        return ExitResponse(event="exit", fee=fee, parked_duration_minutes=parked_duration_minutes)
