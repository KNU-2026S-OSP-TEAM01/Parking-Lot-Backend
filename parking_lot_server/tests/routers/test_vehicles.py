import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entry_exit_log import EntryExitLog
from app.models.parking_lot import ParkingLot
from app.models.vehicle import Vehicle
from app.services.crypto import aes_encrypt, hmac_hash


def _make_vehicle(lot_id: uuid.UUID, plate: str = "12가3456") -> Vehicle:
    return Vehicle(
        id=uuid.uuid4(),
        parking_lot_id=lot_id,
        plate_hash=hmac_hash(plate),
        plate_enc=aes_encrypt(plate),
        entered_at=datetime.now(timezone.utc),
    )


# ── GET /admin/vehicles ───────────────────────────────────────────────────────

async def test_list_vehicles_returns_decrypted_plate(
    client: AsyncClient, superadmin_token, lot, db: AsyncSession
):
    db.add(_make_vehicle(lot.id, "12가3456"))
    await db.flush()

    res = await client.get(
        "/admin/vehicles",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 200
    plates = [v["plate"] for v in res.json()]
    assert "12가3456" in plates


async def test_admin_sees_only_own_lot_vehicles(
    client: AsyncClient, admin_token, lot, db: AsyncSession
):
    # 다른 주차장 차량 추가
    other_lot = ParkingLot(
        id=uuid.uuid4(), name="다른 주차장",
        total_spaces=10, available_spaces=10,
        api_key=uuid.uuid4().hex,
    )
    db.add(other_lot)
    db.add(_make_vehicle(lot.id, "11나1111"))
    db.add(_make_vehicle(other_lot.id, "22다2222"))
    await db.flush()

    res = await client.get(
        "/admin/vehicles",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    lot_ids = {v["parking_lot_id"] for v in res.json()}
    assert lot_ids == {str(lot.id)}


# ── DELETE /admin/vehicles/{vehicle_id} ──────────────────────────────────────

async def test_force_exit_vehicle(
    client: AsyncClient, superadmin_token, lot, db: AsyncSession
):
    vehicle = _make_vehicle(lot.id)
    db.add(vehicle)
    lot.available_spaces -= 1
    await db.flush()

    res = await client.delete(
        f"/admin/vehicles/{vehicle.id}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 204

    # 차량이 삭제됐는지 확인
    from sqlalchemy import select
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle.id))
    assert result.scalar_one_or_none() is None

    # available_spaces 복구 확인
    await db.refresh(lot)
    assert lot.available_spaces == 100  # 99(입차 후) + 1(강제 출차) = 100(원래 상태)

    # 로그에 event_type='admin'으로 기록됐는지 확인
    log_result = await db.execute(
        select(EntryExitLog).where(
            EntryExitLog.plate_hash == vehicle.plate_hash,
            EntryExitLog.event_type == "admin",
        )
    )
    assert log_result.scalar_one_or_none() is not None


async def test_force_exit_wrong_lot_forbidden(
    client: AsyncClient, admin_token, db: AsyncSession
):
    other_lot = ParkingLot(
        id=uuid.uuid4(), name="다른 주차장",
        total_spaces=10, available_spaces=10,
        api_key=uuid.uuid4().hex,
    )
    db.add(other_lot)
    vehicle = _make_vehicle(other_lot.id)
    db.add(vehicle)
    await db.flush()

    res = await client.delete(
        f"/admin/vehicles/{vehicle.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 403


async def test_force_exit_not_found(client: AsyncClient, superadmin_token):
    res = await client.delete(
        f"/admin/vehicles/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 404
