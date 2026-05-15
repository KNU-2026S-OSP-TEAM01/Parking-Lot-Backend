import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entry_exit_log import EntryExitLog
from app.models.vehicle import Vehicle
from app.services.crypto import aes_encrypt, hmac_hash


def _make_vehicle(lot_id, plate="12가3456"):
    return Vehicle(
        id=uuid.uuid4(),
        parking_lot_id=lot_id,
        plate_hash=hmac_hash(plate),
        plate_enc=aes_encrypt(plate),
        entered_at=datetime.now(timezone.utc),
    )


def _auth(token): return {"Authorization": f"Bearer {token}"}


async def test_list_vehicles_returns_decrypted_plate(client: AsyncClient, user_token, lot, db):
    db.add(_make_vehicle(lot.id))
    await db.flush()
    res = await client.get(f"/api/v1/lots/{lot.id}/vehicles", headers=_auth(user_token))
    assert res.status_code == 200
    assert any(v["plate"] == "12가3456" for v in res.json())


async def test_list_vehicles_other_lot_returns_403(client: AsyncClient, other_token, lot):
    res = await client.get(f"/api/v1/lots/{lot.id}/vehicles", headers=_auth(other_token))
    assert res.status_code == 403


async def test_force_exit_vehicle(client: AsyncClient, user_token, lot, db):
    vehicle = _make_vehicle(lot.id)
    lot.available_spaces -= 1
    db.add(vehicle)
    await db.flush()

    res = await client.delete(
        f"/api/v1/lots/{lot.id}/vehicles/{vehicle.id}",
        headers=_auth(user_token),
    )
    assert res.status_code == 204

    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle.id))
    assert result.scalar_one_or_none() is None

    await db.flush()
    await db.refresh(lot)
    assert lot.available_spaces == 100

    log = await db.execute(
        select(EntryExitLog).where(
            EntryExitLog.plate_hash == vehicle.plate_hash,
            EntryExitLog.event_type == "admin",
        )
    )
    assert log.scalar_one_or_none() is not None


async def test_force_exit_other_lot_returns_403(client: AsyncClient, other_token, lot, db):
    vehicle = _make_vehicle(lot.id)
    db.add(vehicle)
    await db.flush()
    res = await client.delete(
        f"/api/v1/lots/{lot.id}/vehicles/{vehicle.id}",
        headers=_auth(other_token),
    )
    assert res.status_code == 403


async def test_force_exit_not_found(client: AsyncClient, user_token, lot):
    res = await client.delete(
        f"/api/v1/lots/{lot.id}/vehicles/{uuid.uuid4()}",
        headers=_auth(user_token),
    )
    assert res.status_code == 404
