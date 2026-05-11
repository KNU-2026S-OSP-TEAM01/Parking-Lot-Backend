import uuid

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


def make_superadmin(password: str = "testpass") -> User:
    return User(
        id=uuid.uuid4(),
        username="superadmin",
        email="superadmin@test.local",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        role="superadmin",
        parking_lot_id=None,
    )


# ── 로그인 ────────────────────────────────────────────────────────────────────

async def test_login_returns_token(client: AsyncClient, db: AsyncSession):
    db.add(make_superadmin("testpass"))
    await db.flush()

    res = await client.post("/admin/login", json={"username": "superadmin", "password": "testpass"})

    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(client: AsyncClient, db: AsyncSession):
    db.add(make_superadmin("testpass"))
    await db.flush()

    res = await client.post("/admin/login", json={"username": "superadmin", "password": "wrong"})

    assert res.status_code == 401
    assert res.json()["detail"] == "invalid_credentials"


async def test_login_unknown_user_returns_401(client: AsyncClient):
    res = await client.post("/admin/login", json={"username": "nobody", "password": "x"})

    assert res.status_code == 401


# ── JWT 페이로드 ──────────────────────────────────────────────────────────────

async def test_jwt_payload_contains_role_and_lot_id(client: AsyncClient, db: AsyncSession):
    from jose import jwt
    from app.config import settings

    db.add(make_superadmin("testpass"))
    await db.flush()

    res = await client.post("/admin/login", json={"username": "superadmin", "password": "testpass"})
    token = res.json()["access_token"]

    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    assert payload["role"] == "superadmin"
    assert payload["lot_id"] is None
    assert "sub" in payload
    assert "exp" in payload


# ── seed 스크립트 동작 검증 ───────────────────────────────────────────────────

async def test_seed_superadmin_is_loginable(client: AsyncClient, db: AsyncSession):
    """seed.py가 생성하는 계정 형식(superadmin/changeme)으로 로그인 가능한지 확인."""
    db.add(User(
        id=uuid.uuid4(),
        username="superadmin",
        email="superadmin@openpark.local",
        password_hash=bcrypt.hashpw(b"changeme", bcrypt.gensalt()).decode(),
        role="superadmin",
    ))
    await db.flush()

    res = await client.post("/admin/login", json={"username": "superadmin", "password": "changeme"})
    assert res.status_code == 200
