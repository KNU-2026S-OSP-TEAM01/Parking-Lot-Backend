"""
superadmin 최초 계정 생성 스크립트.
이미 superadmin이 존재하면 아무 작업도 하지 않는다.

실행:
    python scripts/seed.py
"""
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.entry_exit_log import EntryExitLog  # noqa: F401
from app.models.parking_lot import ParkingLot  # noqa: F401
from app.models.user import User
from app.models.vehicle import Vehicle  # noqa: F401

SUPERADMIN_USERNAME = "superadmin"
SUPERADMIN_EMAIL    = "superadmin@openpark.local"
SUPERADMIN_PASSWORD = "changeme"


async def seed() -> None:
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        result = await session.execute(
            select(User).where(User.role == "superadmin")
        )
        if result.scalar_one_or_none():
            print("superadmin already exists. skipping.")
            return

        user = User(
            id=uuid.uuid4(),
            username=SUPERADMIN_USERNAME,
            email=SUPERADMIN_EMAIL,
            password_hash=bcrypt.hashpw(SUPERADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode(),
            role="superadmin",
            parking_lot_id=None,
        )
        session.add(user)
        await session.commit()

    print(f"superadmin created.")
    print(f"  username : {SUPERADMIN_USERNAME}")
    print(f"  password : {SUPERADMIN_PASSWORD}")
    print("  !! 운영 환경에서는 즉시 비밀번호를 변경하세요.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
