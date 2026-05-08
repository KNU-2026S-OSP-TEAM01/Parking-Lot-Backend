import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


# ── POST /admin/users ─────────────────────────────────────────────────────────

async def test_create_user(client: AsyncClient, superadmin_token, lot):
    res = await client.post(
        "/admin/users",
        json={
            "username": "newadmin",
            "email": "newadmin@test.local",
            "password": "pass1234",
            "parking_lot_id": str(lot.id),
        },
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["username"] == "newadmin"
    assert body["role"] == "admin"
    assert "password" not in body
    assert "password_hash" not in body


async def test_create_user_duplicate_username_returns_409(
    client: AsyncClient, superadmin_token, lot, admin
):
    res = await client.post(
        "/admin/users",
        json={
            "username": admin.username,
            "email": "other@test.local",
            "password": "pass1234",
            "parking_lot_id": str(lot.id),
        },
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 409


async def test_create_user_forbidden_for_admin(client: AsyncClient, admin_token, lot):
    res = await client.post(
        "/admin/users",
        json={
            "username": "another",
            "email": "another@test.local",
            "password": "pass1234",
            "parking_lot_id": str(lot.id),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 403


# ── GET /admin/users ──────────────────────────────────────────────────────────

async def test_list_users(client: AsyncClient, superadmin_token, admin):
    res = await client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 200
    assert any(u["username"] == admin.username for u in res.json())


async def test_list_users_forbidden_for_admin(client: AsyncClient, admin_token):
    res = await client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 403


# ── PATCH /admin/users/{user_id} ──────────────────────────────────────────────

async def test_admin_can_patch_own_account(client: AsyncClient, admin_token, admin):
    res = await client.patch(
        f"/admin/users/{admin.id}",
        json={"email": "updated@test.local"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["email"] == "updated@test.local"


async def test_admin_cannot_patch_other_account(
    client: AsyncClient, admin_token, superadmin
):
    res = await client.patch(
        f"/admin/users/{superadmin.id}",
        json={"email": "hacked@test.local"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 403


# ── DELETE /admin/users/{user_id} ─────────────────────────────────────────────

async def test_delete_user(client: AsyncClient, superadmin_token, admin):
    res = await client.delete(
        f"/admin/users/{admin.id}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert res.status_code == 204


async def test_delete_user_forbidden_for_admin(client: AsyncClient, admin_token, admin):
    res = await client.delete(
        f"/admin/users/{admin.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 403
