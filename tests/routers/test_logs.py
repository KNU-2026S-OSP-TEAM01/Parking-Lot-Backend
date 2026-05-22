import uuid
from datetime import datetime, timezone

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


async def test_filter_logs_by_date_from(client: AsyncClient, user_token, lot, db):

    old_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new_ts = datetime(2026, 5, 1, tzinfo=timezone.utc)

    db.add(EntryExitLog(
        id=uuid.uuid4(), parking_lot_id=lot.id,
        plate_hash=hmac_hash("11가1111"), plate_enc=aes_encrypt("11가1111"),
        event_type="entry", fee=None,
        client_timestamp=old_ts, server_received_at=old_ts,
    ))
    db.add(EntryExitLog(
        id=uuid.uuid4(), parking_lot_id=lot.id,
        plate_hash=hmac_hash("22나2222"), plate_enc=aes_encrypt("22나2222"),
        event_type="entry", fee=None,
        client_timestamp=new_ts, server_received_at=new_ts,
    ))
    await db.flush()

    res = await client.get(
        f"/api/v1/lots/{lot.id}/logs?date_from=2026-03-01",
        headers=_auth(user_token),
    )
    assert res.status_code == 200
    plates = [log["plate"] for log in res.json()]
    assert "22나2222" in plates
    assert "11가1111" not in plates


async def test_filter_logs_by_date_to(client: AsyncClient, user_token, lot, db):
    old_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new_ts = datetime(2026, 5, 1, tzinfo=timezone.utc)

    db.add(EntryExitLog(
        id=uuid.uuid4(), parking_lot_id=lot.id,
        plate_hash=hmac_hash("11가1111"), plate_enc=aes_encrypt("11가1111"),
        event_type="entry", fee=None,
        client_timestamp=old_ts, server_received_at=old_ts,
    ))
    db.add(EntryExitLog(
        id=uuid.uuid4(), parking_lot_id=lot.id,
        plate_hash=hmac_hash("22나2222"), plate_enc=aes_encrypt("22나2222"),
        event_type="entry", fee=None,
        client_timestamp=new_ts, server_received_at=new_ts,
    ))
    await db.flush()

    res = await client.get(
        f"/api/v1/lots/{lot.id}/logs?date_to=2026-03-01",
        headers=_auth(user_token),
    )
    assert res.status_code == 200
    plates = [log["plate"] for log in res.json()]
    assert "11가1111" in plates
    assert "22나2222" not in plates


async def test_logs_offset(client: AsyncClient, user_token, lot, db):
    for i in range(5):
        db.add(_make_log(lot.id, f"1{i}가0000"))
    await db.flush()

    res_all  = await client.get(f"/api/v1/lots/{lot.id}/logs?limit=5&offset=0", headers=_auth(user_token))
    res_skip = await client.get(f"/api/v1/lots/{lot.id}/logs?limit=5&offset=3", headers=_auth(user_token))
    assert len(res_all.json())  == 5
    assert len(res_skip.json()) == 2
