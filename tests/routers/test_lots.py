import uuid
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

LOT_PAYLOAD = {
    "name": "신규 주차장",
    "address": "서울시 강남구 테헤란로 1",
    "total_spaces": 50,
    "base_fee": 1000,
    "base_duration_minutes": 30,
    "extra_fee_per_unit": 200,
    "extra_fee_unit_minutes": 10,
}

_MOCK_GEOCODE = patch(
    "app.routers.lots.geocode",
    new_callable=AsyncMock,
    return_value=(37.5665, 126.9780),
)


def _auth(token): return {"Authorization": f"Bearer {token}"}


# ── POST /api/v1/lots ─────────────────────────────────────────────────────────

async def test_create_lot(client: AsyncClient, user_token):
    with _MOCK_GEOCODE:
        res = await client.post("/api/v1/lots", json=LOT_PAYLOAD, headers=_auth(user_token))
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "신규 주차장"
    assert body["available_spaces"] == 50
    assert body["latitude"] == 37.5665
    assert body["longitude"] == 126.9780


async def test_create_lot_sets_owner(client: AsyncClient, user, user_token):
    with _MOCK_GEOCODE:
        res = await client.post("/api/v1/lots", json=LOT_PAYLOAD, headers=_auth(user_token))
    assert res.json()["owner_user_id"] == str(user.id)


async def test_create_lot_requires_auth(client: AsyncClient):
    res = await client.post("/api/v1/lots", json=LOT_PAYLOAD)
    assert res.status_code == 401


# ── GET /api/v1/lots ──────────────────────────────────────────────────────────

async def test_list_lots_returns_only_own(client: AsyncClient, user_token, lot, other_token, other_user, db):
    from app.models.parking_lot import ParkingLot
    other_lot = ParkingLot(
        id=uuid.uuid4(), owner_user_id=other_user.id,
        name="타인 주차장", address="부산시 해운대구 1", total_spaces=10, available_spaces=10,
        latitude=35.1631, longitude=129.1639, api_key=uuid.uuid4().hex,
    )
    db.add(other_lot)
    await db.flush()

    res = await client.get("/api/v1/lots", headers=_auth(user_token))
    assert res.status_code == 200
    ids = {item["id"] for item in res.json()}
    assert str(lot.id) in ids
    assert str(other_lot.id) not in ids


async def test_list_lots_returns_full_api_key(client: AsyncClient, user_token, lot):
    res = await client.get("/api/v1/lots", headers=_auth(user_token))
    for item in res.json():
        assert len(item["api_key"]) == 64


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


async def test_delete_nonexistent_lot_returns_404(client: AsyncClient, user_token):
    import uuid
    res = await client.delete(f"/api/v1/lots/{uuid.uuid4()}", headers=_auth(user_token))
    assert res.status_code == 404


async def test_invalid_jwt_returns_401(client: AsyncClient, lot):
    res = await client.get("/api/v1/lots", headers=_auth("invalid.jwt.token"))
    assert res.status_code == 401


async def test_patch_total_spaces_recalculates_available(
    client: AsyncClient, user_token, lot, db
):
    """total_spaces 변경 시 available_spaces = new_total - parked 로 재계산되어야 한다."""
    from app.models.vehicle import Vehicle
    from app.services.crypto import aes_encrypt, hmac_hash
    from datetime import datetime, timezone

    # 차량 20대 주차
    for i in range(20):
        db.add(Vehicle(
            parking_lot_id=lot.id,
            plate_hash=hmac_hash(f"2{i}가0000"),
            plate_enc=aes_encrypt(f"2{i}가0000"),
            entered_at=datetime.now(timezone.utc),
        ))
    lot.available_spaces -= 20
    await db.flush()

    # total_spaces 100 → 50 (주차 중 20대, 잔여 30)
    res = await client.patch(
        f"/api/v1/lots/{lot.id}",
        json={"total_spaces": 50},
        headers=_auth(user_token),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total_spaces"] == 50
    assert body["available_spaces"] == 30  # 50 - 20
