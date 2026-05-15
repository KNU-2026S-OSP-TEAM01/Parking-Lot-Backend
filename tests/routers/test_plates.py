import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entry_exit_log import EntryExitLog
from app.models.vehicle import Vehicle

PLATE = "12가3456"
TIMESTAMP = "2026-05-01T10:00:00+09:00"


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


# ── 인증 ──────────────────────────────────────────────────────────────────────

async def test_invalid_api_key_returns_401(client: AsyncClient):
    res = await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": TIMESTAMP},
        headers=_headers("invalid_key"),
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid_api_key"


async def test_inactive_lot_returns_401(client: AsyncClient, db: AsyncSession, lot):
    lot.is_active = False
    await db.flush()

    res = await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": TIMESTAMP},
        headers=_headers(lot.api_key),
    )
    assert res.status_code == 401


# ── 입차 ──────────────────────────────────────────────────────────────────────

async def test_entry_returns_event_and_entered_at(client: AsyncClient, lot):
    res = await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": TIMESTAMP},
        headers=_headers(lot.api_key),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["event"] == "entry"
    assert "entered_at" in body


async def test_entry_decrements_available_spaces(
    client: AsyncClient, lot, db: AsyncSession
):
    before = lot.available_spaces
    await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": TIMESTAMP},
        headers=_headers(lot.api_key),
    )
    await db.flush()
    await db.refresh(lot)
    assert lot.available_spaces == before - 1


async def test_entry_creates_vehicle_record(
    client: AsyncClient, lot, db: AsyncSession
):
    await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": TIMESTAMP},
        headers=_headers(lot.api_key),
    )
    result = await db.execute(select(Vehicle).where(Vehicle.parking_lot_id == lot.id))
    assert result.scalar_one_or_none() is not None


async def test_entry_logs_event(client: AsyncClient, lot, db: AsyncSession):
    await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": TIMESTAMP},
        headers=_headers(lot.api_key),
    )
    result = await db.execute(
        select(EntryExitLog).where(
            EntryExitLog.parking_lot_id == lot.id,
            EntryExitLog.event_type == "entry",
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_entry_full_lot_returns_409(client: AsyncClient, lot, db: AsyncSession):
    lot.available_spaces = 0
    await db.flush()

    res = await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": TIMESTAMP},
        headers=_headers(lot.api_key),
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "parking_lot_full"


# ── 출차 ──────────────────────────────────────────────────────────────────────

async def _do_entry(client: AsyncClient, api_key: str, plate: str, timestamp: str):
    return await client.post(
        "/api/v1/plates",
        json={"plate": plate, "timestamp": timestamp},
        headers=_headers(api_key),
    )


async def test_exit_returns_fee_and_duration(client: AsyncClient, lot):
    await _do_entry(client, lot.api_key, PLATE, "2026-05-01T10:00:00+09:00")

    res = await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": "2026-05-01T11:00:00+09:00"},
        headers=_headers(lot.api_key),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["event"] == "exit"
    assert body["parked_duration_minutes"] == 60
    assert "fee" in body


async def test_exit_restores_available_spaces(
    client: AsyncClient, lot, db: AsyncSession
):
    before = lot.available_spaces
    await _do_entry(client, lot.api_key, PLATE, "2026-05-01T10:00:00+09:00")

    await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": "2026-05-01T11:00:00+09:00"},
        headers=_headers(lot.api_key),
    )
    await db.flush()
    await db.refresh(lot)
    assert lot.available_spaces == before


async def test_exit_removes_vehicle_record(
    client: AsyncClient, lot, db: AsyncSession
):
    await _do_entry(client, lot.api_key, PLATE, "2026-05-01T10:00:00+09:00")
    await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": "2026-05-01T11:00:00+09:00"},
        headers=_headers(lot.api_key),
    )
    result = await db.execute(select(Vehicle).where(Vehicle.parking_lot_id == lot.id))
    assert result.scalar_one_or_none() is None


async def test_exit_logs_event(client: AsyncClient, lot, db: AsyncSession):
    await _do_entry(client, lot.api_key, PLATE, "2026-05-01T10:00:00+09:00")
    await client.post(
        "/api/v1/plates",
        json={"plate": PLATE, "timestamp": "2026-05-01T11:00:00+09:00"},
        headers=_headers(lot.api_key),
    )
    result = await db.execute(
        select(EntryExitLog).where(
            EntryExitLog.parking_lot_id == lot.id,
            EntryExitLog.event_type == "exit",
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_entered_at_uses_client_timestamp(
    client: AsyncClient, lot, db: AsyncSession
):
    """entered_at은 서버 시각이 아닌 클라이언트 전송 timestamp를 사용해야 한다."""
    await _do_entry(client, lot.api_key, PLATE, "2026-05-01T10:00:00+09:00")

    result = await db.execute(select(Vehicle).where(Vehicle.parking_lot_id == lot.id))
    vehicle = result.scalar_one()
    assert vehicle.entered_at.hour == 1  # 10:00 KST = 01:00 UTC
