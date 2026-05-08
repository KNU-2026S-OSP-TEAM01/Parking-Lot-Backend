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
    """
    각 테스트마다 독립된 DB 환경을 제공한다.
    - 테스트 시작: 테이블 생성
    - 테스트 실행: 트랜잭션 내에서 수행
    - 테스트 종료: 롤백 후 테이블 삭제
    """
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
    """
    테스트용 HTTP 클라이언트.
    get_db 의존성을 테스트 세션으로 교체해 라우터가 테스트 DB를 사용하도록 한다.
    """
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── 공용 픽스처 ───────────────────────────────────────────────────────────────

def _make_token(user_id: uuid.UUID, role: str, lot_id: uuid.UUID | None) -> str:
    payload = {
        "sub":    str(user_id),
        "role":   role,
        "lot_id": str(lot_id) if lot_id else None,
        "exp":    datetime.now(timezone.utc) + timedelta(hours=8),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


@pytest.fixture
async def superadmin(db):
    user = User(
        id=uuid.uuid4(),
        username="superadmin",
        email="superadmin@test.local",
        password_hash=bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode(),
        role="superadmin",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
def superadmin_token(superadmin):
    return _make_token(superadmin.id, "superadmin", None)


@pytest.fixture
async def lot(db):
    """테스트용 주차장."""
    parking_lot = ParkingLot(
        id=uuid.uuid4(),
        name="테스트 주차장",
        total_spaces=100,
        available_spaces=100,
        api_key=uuid.uuid4().hex,
    )
    db.add(parking_lot)
    await db.flush()
    return parking_lot


@pytest.fixture
async def admin(db, lot):
    """특정 주차장에 할당된 admin 계정."""
    user = User(
        id=uuid.uuid4(),
        username="admin1",
        email="admin1@test.local",
        password_hash=bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode(),
        role="admin",
        parking_lot_id=lot.id,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
def admin_token(admin, lot):
    return _make_token(admin.id, "admin", lot.id)
