import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.models.entry_exit_log import EntryExitLog
from app.services.crypto import aes_encrypt, hmac_hash


def _make_log(lot_id, plate="12가3456", event_type="entry"):
    now = datetime.now(timezone.utc)
    return EntryExitLog(
        id=uuid.uuid4(),
        parking_lot_id=lot_id,
        plate_hash=hmac_hash(plate),
        plate_enc=aes_encrypt(plate),
        event_type=event_type,
        fee=None if event_type != "exit" else 3000,
        client_timestamp=now,
        server_received_at=now,
    )


def _auth(token): return {"Authorization": f"Bearer {token}"}


async def test_list_logs_returns_decrypted_plate(client: AsyncClient, user_token, lot, db):
    db.add(_make_log(lot.id))
    await db.flush()
    res = await client.get(f"/api/v1/lots/{lot.id}/logs", headers=_auth(user_token))
    assert res.status_code == 200
    assert any(log["plate"] == "12가3456" for log in res.json())


async def test_list_logs_other_lot_returns_403(client: AsyncClient, other_token, lot):
    res = await client.get(f"/api/v1/lots/{lot.id}/logs", headers=_auth(other_token))
    assert res.status_code == 403


async def test_filter_logs_by_plate(client: AsyncClient, user_token, lot, db):
    db.add(_make_log(lot.id, "12가3456"))
    db.add(_make_log(lot.id, "99나9999"))
    await db.flush()
    res = await client.get(f"/api/v1/lots/{lot.id}/logs?plate=12가3456", headers=_auth(user_token))
    assert res.status_code == 200
    assert all(log["plate"] == "12가3456" for log in res.json())


async def test_filter_logs_by_event_type(client: AsyncClient, user_token, lot, db):
    db.add(_make_log(lot.id, event_type="entry"))
    db.add(_make_log(lot.id, event_type="exit"))
    await db.flush()
    res = await client.get(f"/api/v1/lots/{lot.id}/logs?event_type=exit", headers=_auth(user_token))
    assert res.status_code == 200
    assert all(log["event_type"] == "exit" for log in res.json())


async def test_logs_pagination(client: AsyncClient, user_token, lot, db):
    for i in range(5):
        db.add(_make_log(lot.id, f"1{i}가0000"))
    await db.flush()
    res = await client.get(f"/api/v1/lots/{lot.id}/logs?limit=2&offset=0", headers=_auth(user_token))
    assert len(res.json()) == 2
