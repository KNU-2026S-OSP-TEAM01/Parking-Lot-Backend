import uuid
import logging

import httpx
from fastapi import HTTPException

from app.config import settings
from app.models.parking_lot import ParkingLot

logger = logging.getLogger(__name__)


async def notify_hub_lot_created(lot: ParkingLot) -> None:
    """lot 생성 시 Hub에 push. 실패하면 HTTPException(503) 발생 → lot 생성 롤백."""
    payload = {
        "pls_url":               str(settings.hub_url).rstrip("/"),
        "lot_id":                str(lot.id),
        "name":                  lot.name,
        "address":               lot.address,
        "total_spaces":          lot.total_spaces,
        "base_fee":              lot.base_fee,
        "base_duration_minutes": lot.base_duration_minutes,
        "extra_fee_per_unit":    lot.extra_fee_per_unit,
        "extra_fee_unit_minutes":lot.extra_fee_unit_minutes,
        "daily_max_fee":         lot.daily_max_fee,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(f"{settings.hub_url}/lots", json=payload)
            if res.status_code not in (200, 201):
                raise HTTPException(
                    status_code=503,
                    detail=f"hub_registration_failed: {res.status_code}",
                )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"hub_unreachable: {e}")


async def notify_hub_lot_deactivated(lot_id: uuid.UUID) -> None:
    """lot 비활성화 시 Hub에 알림. 실패해도 PLS 비활성화는 유지 (best-effort)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.patch(
                f"{settings.hub_url}/lots/{lot_id}",
                json={"is_active": False},
            )
    except Exception as e:
        logger.warning("Hub deactivation notify failed for lot %s: %s", lot_id, e)
