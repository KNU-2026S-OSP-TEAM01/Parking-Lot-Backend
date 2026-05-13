import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

LOT_PAYLOAD = {
    "name": "신규 주차장",
    "total_spaces": 50,
    "base_fee": 1000,
    "base_duration_minutes": 30,
    "extra_fee_per_unit": 200,
    "extra_fee_unit_minutes": 10,
}


def _auth(token): return {"Authorization": f"Bearer {token}"}


# ── POST /api/v1/lots ─────────────────────────────────────────────────────────

async def test_create_lot(client: AsyncClient, user_token):
    res = await client.post("/api/v1/lots", json=LOT_PAYLOAD, headers=_auth(user_token))
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "신규 주차장"
    assert body["available_spaces"] == 50
    assert "..." not in body["api_key"]  # 최초 등록 시 원문 반환


async def test_create_lot_sets_owner(client: AsyncClient, user, user_token):
    res = await client.post("/api/v1/lots", json=LOT_PAYLOAD, headers=_auth(user_token))
    assert res.json()["owner_user_id"] == str(user.id)


async def test_create_lot_requires_auth(client: AsyncClient):
    res = await client.post("/api/v1/lots", json=LOT_PAYLOAD)
    assert res.status_code == 401


# ── GET /api/v1/lots ──────────────────────────────────────────────────────────

async def test_list_lots_returns_only_own(client: AsyncClient, user_token, lot, other_token, other_user, db):
    from app.models.parking_lot import ParkingLot
    other_lot = ParkingLot(id=uuid.uuid4(), owner_user_id=other_user.id,
                           name="타인 주차장", total_spaces=10, available_spaces=10,
                           api_key=uuid.uuid4().hex)
    db.add(other_lot)
    await db.flush()

    res = await client.get("/api/v1/lots", headers=_auth(user_token))
    assert res.status_code == 200
    ids = {item["id"] for item in res.json()}
    assert str(lot.id) in ids
    assert str(other_lot.id) not in ids


async def test_list_lots_api_key_is_masked(client: AsyncClient, user_token, lot):
    res = await client.get("/api/v1/lots", headers=_auth(user_token))
    for item in res.json():
        assert "..." in item["api_key"]


# ── GET /api/v1/lots/{lot_id} ────────────────────────────────────────────────

async def test_get_own_lot(client: AsyncClient, user_token, lot):
    res = await client.get(f"/api/v1/lots/{lot.id}", headers=_auth(user_token))
    assert res.status_code == 200
    assert res.json()["id"] == str(lot.id)


async def test_get_other_lot_returns_403(client: AsyncClient, other_token, lot):
    res = await client.get(f"/api/v1/lots/{lot.id}", headers=_auth(other_token))
    assert res.status_code == 403


async def test_get_nonexistent_lot_returns_404(client: AsyncClient, user_token):
    res = await client.get(f"/api/v1/lots/{uuid.uuid4()}", headers=_auth(user_token))
    assert res.status_code == 404


# ── PATCH /api/v1/lots/{lot_id} ──────────────────────────────────────────────

async def test_patch_lot(client: AsyncClient, user_token, lot):
    res = await client.patch(f"/api/v1/lots/{lot.id}", json={"name": "수정됨"}, headers=_auth(user_token))
    assert res.status_code == 200
    assert res.json()["name"] == "수정됨"


async def test_patch_other_lot_returns_403(client: AsyncClient, other_token, lot):
    res = await client.patch(f"/api/v1/lots/{lot.id}", json={"name": "x"}, headers=_auth(other_token))
    assert res.status_code == 403


async def test_patch_total_spaces_below_parked_count_returns_400(
    client: AsyncClient, user_token, lot, db
):
    """주차 중인 차량 수보다 total_spaces를 낮게 설정하면 400."""
    from app.models.vehicle import Vehicle
    from app.services.crypto import aes_encrypt, hmac_hash
    from datetime import datetime, timezone

    # 차량 10대 주차 (available_spaces: 100 → 90)
    for i in range(10):
        db.add(Vehicle(
            parking_lot_id=lot.id,
            plate_hash=hmac_hash(f"1{i}가0000"),
            plate_enc=aes_encrypt(f"1{i}가0000"),
            entered_at=datetime.now(timezone.utc),
        ))
    lot.available_spaces -= 10
    await db.flush()

    # total_spaces=9: 주차 중(10)보다 작으므로 400
    res = await client.patch(f"/api/v1/lots/{lot.id}", json={"total_spaces": 9}, headers=_auth(user_token))
    assert res.status_code == 400

    # total_spaces=10: 주차 중(10)과 같으므로 허용
    res = await client.patch(f"/api/v1/lots/{lot.id}", json={"total_spaces": 10}, headers=_auth(user_token))
    assert res.status_code == 200


# ── DELETE /api/v1/lots/{lot_id} ─────────────────────────────────────────────

async def test_delete_lot(client: AsyncClient, user_token, lot, db):
    res = await client.delete(f"/api/v1/lots/{lot.id}", headers=_auth(user_token))
    assert res.status_code == 204

    from sqlalchemy import select
    from app.models.parking_lot import ParkingLot
    result = await db.execute(select(ParkingLot).where(ParkingLot.id == lot.id))
    assert result.scalar_one_or_none() is None


async def test_delete_other_lot_returns_403(client: AsyncClient, other_token, lot):
    res = await client.delete(f"/api/v1/lots/{lot.id}", headers=_auth(other_token))
    assert res.status_code == 403
