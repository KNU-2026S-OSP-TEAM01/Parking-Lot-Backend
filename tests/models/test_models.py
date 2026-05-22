import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.entry_exit_log import EntryExitLog
from app.models.parking_lot import ParkingLot
from app.models.user import User
from app.models.vehicle import Vehicle


# ── 구조 테스트 (DB 불필요) ────────────────────────────────────────────────────

def test_table_names():
    assert User.__tablename__ == "users"
    assert ParkingLot.__tablename__ == "parking_lots"
    assert Vehicle.__tablename__ == "vehicles"
    assert EntryExitLog.__tablename__ == "entry_exit_logs"


def test_user_has_no_role_or_parking_lot_id():
    cols = {c.name for c in User.__table__.columns}
    assert "role" not in cols
    assert "parking_lot_id" not in cols


def test_parking_lot_has_owner_user_id():
    cols = {c.name for c in ParkingLot.__table__.columns}
    assert "owner_user_id" in cols


def test_vehicle_has_bytea_plate_enc():
    from sqlalchemy import LargeBinary
    col = Vehicle.__table__.columns["plate_enc"]
    assert isinstance(col.type, LargeBinary)


def test_datetime_columns_are_timezone_aware():
    from sqlalchemy import DateTime
    tz_cols = [
        ParkingLot.__table__.columns["created_at"],
        ParkingLot.__table__.columns["updated_at"],
        User.__table__.columns["created_at"],
        Vehicle.__table__.columns["entered_at"],
        EntryExitLog.__table__.columns["client_timestamp"],
        EntryExitLog.__table__.columns["server_received_at"],
    ]
    for col in tz_cols:
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True, f"{col.name} has no timezone"


# ── DB 통합 테스트 ─────────────────────────────────────────────────────────────

def _make_user(**kwargs) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        username=f"user_{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hashed",
    )
    return User(**{**defaults, **kwargs})


def _make_lot(user_id, **kwargs) -> ParkingLot:
    defaults = dict(
        id=uuid.uuid4(),
        owner_user_id=user_id,
        name="테스트 주차장",
        total_spaces=100,
        available_spaces=100,
        api_key=uuid.uuid4().hex,
    )
    return ParkingLot(**{**defaults, **kwargs})


async def test_create_user(db):
    user = _make_user()
    db.add(user)
    await db.flush()
    result = await db.get(User, user.id)
    assert result.username == user.username


async def test_user_username_unique(db):
    db.add(_make_user(username="dup"))
    await db.flush()
    db.add(_make_user(username="dup"))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_create_parking_lot_with_owner(db):
    user = _make_user()
    db.add(user)
    await db.flush()

    lot = _make_lot(user.id)
    db.add(lot)
    await db.flush()

    result = await db.get(ParkingLot, lot.id)
    assert result.owner_user_id == user.id


async def test_parking_lot_available_lte_total_constraint(db):
    user = _make_user()
    db.add(user)
    await db.flush()

    db.add(_make_lot(user.id, total_spaces=10, available_spaces=11))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_api_key_unique_constraint(db):
    user = _make_user()
    db.add(user)
    await db.flush()

    key = uuid.uuid4().hex
    db.add(_make_lot(user.id, api_key=key))
    await db.flush()
    db.add(_make_lot(user.id, api_key=key))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_vehicle_unique_per_lot(db):
    user = _make_user()
    db.add(user)
    await db.flush()
    lot = _make_lot(user.id)
    db.add(lot)
    await db.flush()

    now = datetime.now(timezone.utc)
    db.add(Vehicle(parking_lot_id=lot.id, plate_hash="abc", plate_enc=b"enc", entered_at=now))
    await db.flush()
    db.add(Vehicle(parking_lot_id=lot.id, plate_hash="abc", plate_enc=b"enc", entered_at=now))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_entry_exit_log_invalid_event_type(db):
    user = _make_user()
    db.add(user)
    await db.flush()
    lot = _make_lot(user.id)
    db.add(lot)
    await db.flush()

    now = datetime.now(timezone.utc)
    db.add(EntryExitLog(
        parking_lot_id=lot.id,
        plate_hash="abc",
        plate_enc=b"enc",
        event_type="wrong",
        client_timestamp=now,
        server_received_at=now,
    ))
    with pytest.raises(IntegrityError):
        await db.flush()
