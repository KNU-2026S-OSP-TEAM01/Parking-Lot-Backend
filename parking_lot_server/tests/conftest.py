import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.database import Base
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
