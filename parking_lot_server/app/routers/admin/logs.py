from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.jwt_auth import get_current_user
from app.models.entry_exit_log import EntryExitLog
from app.schemas.log import LogOut
from app.services.crypto import aes_decrypt, hmac_hash

router = APIRouter()


@router.get("/logs", response_model=list[LogOut])
async def list_logs(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    plate:     Optional[str]  = Query(None),
    limit:     int            = Query(50, le=200),
    offset:    int            = Query(0, ge=0),
) -> list[LogOut]:
    query = select(EntryExitLog).order_by(EntryExitLog.client_timestamp.desc())

    if user["role"] == "admin":
        query = query.where(EntryExitLog.parking_lot_id == user["lot_id"])
    if date_from:
        query = query.where(EntryExitLog.client_timestamp >= date_from)
    if date_to:
        query = query.where(EntryExitLog.client_timestamp <= date_to)
    if plate:
        # 번호판 원문 → HMAC 해시 후 plate_hash와 비교 (암호화된 컬럼은 LIKE 검색 불가)
        query = query.where(EntryExitLog.plate_hash == hmac_hash(plate))

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
