import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entry_exit_log import EntryExitLog
from app.services.crypto import aes_encrypt, hmac_hash


def _make_log(
    lot_id: uuid.UUID,
    plate: str = "12가3456",
    event_type: str = "entry",
    fee: int | None = None,
) -> EntryExitLog:
    now = datetime.now(timezone.utc)
    return EntryExitLog(
        id=uuid.uuid4(),
        parking_lot_id=lot_id,
        plate_hash=hmac_hash(plate),
        plate_enc=aes_encrypt(plate),
        event_type=event_type,
        fee=fee,
        client_timestamp=now,
        server_received_at=now,
    )


# ── GET /admin/logs ───────────────────────────────────────────────────────────

async def test_list_logs_returns_decrypted_plate(
    client: AsyncClient, superadmin_token, lot, db: AsyncSession
):
    db.add(_make_log(lot.id, "12가3456", "entry"))
    await db.flush()

    res = await client.get(
        "/admin/logs",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 200
    plates = [log["plate"] for log in res.json()]
    assert "12가3456" in plates


async def test_admin_sees_only_own_lot_logs(
    client: AsyncClient, admin_token, lot, db: AsyncSession
):
    from app.models.parking_lot import ParkingLot
    other_lot = ParkingLot(
        id=uuid.uuid4(), name="다른 주차장",
        total_spaces=10, available_spaces=10,
        api_key=uuid.uuid4().hex,
    )
    db.add(other_lot)
    await db.flush()  # other_lot이 먼저 저장돼야 FK 참조 가능
    db.add(_make_log(lot.id))
    db.add(_make_log(other_lot.id))
    await db.flush()

    res = await client.get(
        "/admin/logs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    lot_ids = {log["parking_lot_id"] for log in res.json()}
    assert lot_ids == {str(lot.id)}


async def test_search_logs_by_plate(
    client: AsyncClient, superadmin_token, lot, db: AsyncSession
):
    db.add(_make_log(lot.id, "12가3456"))
    db.add(_make_log(lot.id, "99나9999"))
    await db.flush()

    res = await client.get(
        "/admin/logs?plate=12가3456",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 200
    assert all(log["plate"] == "12가3456" for log in res.json())


async def test_logs_pagination(
    client: AsyncClient, superadmin_token, lot, db: AsyncSession
):
    for i in range(5):
        db.add(_make_log(lot.id, f"1{i}가0000"))
    await db.flush()

    res = await client.get(
        "/admin/logs?limit=2&offset=0",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 200
    assert len(res.json()) == 2


async def test_logs_requires_auth(client: AsyncClient):
    res = await client.get("/admin/logs")
    assert res.status_code == 401
