import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.parking_lot import ParkingLot
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.entry_exit_log import EntryExitLog


@pytest.fixture
async def db():
    engine = create_async_engine(settings.test_database_url, connect_args={"ssl": False})

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with engine.connect() as conn:
            await conn.begin()
            async with async_sessionmaker(bind=conn, expire_on_commit=False)() as session:
                yield session
            await conn.rollback()
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── 공용 픽스처 ───────────────────────────────────────────────────────────────

def _make_token(user_id: uuid.UUID) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


@pytest.fixture
async def user(db):
    u = User(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash=bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode(),
    )
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
def user_token(user):
    return _make_token(user.id)


@pytest.fixture
async def lot(db, user):
    parking_lot = ParkingLot(
        id=uuid.uuid4(),
        owner_user_id=user.id,
        name="테스트 주차장",
        total_spaces=100,
        available_spaces=100,
        api_key=uuid.uuid4().hex,
    )
    db.add(parking_lot)
    await db.flush()
    return parking_lot


@pytest.fixture
async def other_user(db):
    u = User(
        id=uuid.uuid4(),
        username="other",
        email="other@example.com",
        password_hash=bcrypt.hashpw(b"pass", bcrypt.gensalt()).decode(),
    )
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
def other_token(other_user):
    return _make_token(other_user.id)
