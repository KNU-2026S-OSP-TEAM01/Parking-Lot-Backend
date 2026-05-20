import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


# ── 회원가입 ──────────────────────────────────────────────────────────────────

async def test_signup_creates_user(client: AsyncClient):
    res = await client.post("/api/v1/signup", json={
        "username": "newuser",
        "email": "new@example.com",
        "password": "pass1234",
    })
    assert res.status_code == 201
    body = res.json()
    assert body["username"] == "newuser"
    assert "role" not in body
    assert "parking_lot_id" not in body


async def test_signup_duplicate_username_returns_409(client: AsyncClient):
    payload = {"username": "dup", "email": "a@example.com", "password": "pass"}
    await client.post("/api/v1/signup", json=payload)
    res = await client.post("/api/v1/signup", json={"username": "dup", "email": "b@example.com", "password": "pass"})
    assert res.status_code == 409
    assert res.json()["detail"] == "username_already_exists"


async def test_signup_duplicate_email_returns_409(client: AsyncClient):
    payload = {"username": "a", "email": "same@example.com", "password": "pass"}
    await client.post("/api/v1/signup", json=payload)
    res = await client.post("/api/v1/signup", json={"username": "b", "email": "same@example.com", "password": "pass"})
    assert res.status_code == 409
    assert res.json()["detail"] == "email_already_exists"


async def test_signup_disabled_returns_403(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("app.routers.auth.settings.enable_signup", False)
    res = await client.post("/api/v1/signup", json={
        "username": "x", "email": "x@example.com", "password": "x"
    })
    assert res.status_code == 403
    assert res.json()["detail"] == "signup_disabled"


# ── 로그인 ────────────────────────────────────────────────────────────────────

async def test_login_returns_token(client: AsyncClient, user):
    res = await client.post("/api/v1/login", json={"username": "testuser", "password": "testpass"})
    assert res.status_code == 200
    assert "access_token" in res.json()
    assert res.json()["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(client: AsyncClient, user):
    res = await client.post("/api/v1/login", json={"username": "testuser", "password": "wrong"})
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid_credentials"


async def test_login_unknown_user_returns_401(client: AsyncClient):
    res = await client.post("/api/v1/login", json={"username": "nobody", "password": "x"})
    assert res.status_code == 401


async def test_jwt_has_no_role_field(client: AsyncClient, user):
    from jose import jwt
    res = await client.post("/api/v1/login", json={"username": "testuser", "password": "testpass"})
    token = res.json()["access_token"]
    payload = jwt.decode(token, "secret", options={"verify_signature": False})
    assert "role" not in payload
    assert "sub" in payload
