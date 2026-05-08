import pytest
from httpx import AsyncClient


LOT_PAYLOAD = {
    "name": "신규 주차장",
    "total_spaces": 50,
    "base_fee": 1000,
    "base_duration_minutes": 30,
    "extra_fee_per_unit": 200,
    "extra_fee_unit_minutes": 10,
}


# ── POST /admin/lots ──────────────────────────────────────────────────────────

async def test_create_lot_returns_full_api_key(client: AsyncClient, superadmin_token):
    res = await client.post(
        "/admin/lots",
        json=LOT_PAYLOAD,
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "신규 주차장"
    assert body["available_spaces"] == 50
    # 최초 등록 시 api_key 원문 반환 (마스킹 없음)
    assert "..." not in body["api_key"]
    assert len(body["api_key"]) == 64


async def test_create_lot_forbidden_for_admin(client: AsyncClient, admin_token):
    res = await client.post(
        "/admin/lots",
        json=LOT_PAYLOAD,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 403


async def test_create_lot_requires_auth(client: AsyncClient):
    res = await client.post("/admin/lots", json=LOT_PAYLOAD)
    assert res.status_code == 401


# ── GET /admin/lots ───────────────────────────────────────────────────────────

async def test_superadmin_gets_all_lots(client: AsyncClient, superadmin_token, lot):
    res = await client.get(
        "/admin/lots",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 200
    assert len(res.json()) >= 1


async def test_admin_gets_only_own_lot(client: AsyncClient, admin_token, lot):
    res = await client.get(
        "/admin/lots",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    ids = [item["id"] for item in res.json()]
    assert all(i == str(lot.id) for i in ids)


async def test_list_lots_api_key_is_masked(client: AsyncClient, superadmin_token, lot):
    res = await client.get(
        "/admin/lots",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    for item in res.json():
        assert "..." in item["api_key"]


# ── GET /admin/lots/{lot_id} ──────────────────────────────────────────────────

async def test_get_lot_by_id(client: AsyncClient, superadmin_token, lot):
    res = await client.get(
        f"/admin/lots/{lot.id}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["id"] == str(lot.id)


async def test_admin_cannot_get_other_lot(client: AsyncClient, admin_token, superadmin, db):
    import uuid
    from app.models.parking_lot import ParkingLot
    other_lot = ParkingLot(
        id=uuid.uuid4(), name="다른 주차장",
        total_spaces=10, available_spaces=10,
        api_key=uuid.uuid4().hex,
    )
    db.add(other_lot)
    await db.flush()

    res = await client.get(
        f"/admin/lots/{other_lot.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 403


async def test_get_lot_not_found(client: AsyncClient, superadmin_token):
    import uuid
    res = await client.get(
        f"/admin/lots/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 404


# ── PATCH /admin/lots/{lot_id} ────────────────────────────────────────────────

async def test_patch_lot_name(client: AsyncClient, superadmin_token, lot):
    res = await client.patch(
        f"/admin/lots/{lot.id}",
        json={"name": "수정된 이름"},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "수정된 이름"


async def test_patch_total_spaces_below_available_returns_400(
    client: AsyncClient, superadmin_token, lot
):
    # available_spaces=100인 상태에서 total_spaces를 50으로 줄이면 안 됨
    res = await client.patch(
        f"/admin/lots/{lot.id}",
        json={"total_spaces": 50},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 400


# ── DELETE /admin/lots/{lot_id} ───────────────────────────────────────────────

async def test_deactivate_lot(client: AsyncClient, superadmin_token, lot):
    res = await client.delete(
        f"/admin/lots/{lot.id}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 204

    # 비활성화됐는지 확인
    get_res = await client.get(
        f"/admin/lots/{lot.id}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert get_res.json()["is_active"] is False


async def test_deactivate_lot_forbidden_for_admin(client: AsyncClient, admin_token, lot):
    res = await client.delete(
        f"/admin/lots/{lot.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 403
