import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.models.entry_exit_log import EntryExitLog
from app.models.parking_lot import ParkingLot
from app.models.user import User
from app.models.vehicle import Vehicle


# ── 구조 테스트 (DB 불필요) ────────────────────────────────────────────────────

def test_table_names():
    assert ParkingLot.__tablename__ == "parking_lots"
    assert User.__tablename__ == "users"
    assert Vehicle.__tablename__ == "vehicles"
    assert EntryExitLog.__tablename__ == "entry_exit_logs"


def test_parking_lot_columns():
    cols = {c.name for c in ParkingLot.__table__.columns}
    assert {"id", "name", "total_spaces", "available_spaces",
            "base_fee", "base_duration_minutes", "extra_fee_per_unit",
            "extra_fee_unit_minutes", "daily_max_fee",
            "api_key", "is_active"} <= cols


def test_vehicle_has_bytea_plate_enc():
    col = Vehicle.__table__.columns["plate_enc"]
    from sqlalchemy import LargeBinary
    assert isinstance(col.type, LargeBinary)


def test_datetime_columns_are_timezone_aware():
    """모든 시각 컬럼이 timezone=True인지 확인."""
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
        assert isinstance(col.type, DateTime), f"{col.name} is not DateTime"
        assert col.type.timezone is True, f"{col.name} has no timezone"


# ── DB 통합 테스트 ─────────────────────────────────────────────────────────────

def _make_lot(**kwargs) -> ParkingLot:
    defaults = dict(
        id=uuid.uuid4(),
        name="테스트 주차장",
        total_spaces=100,
        available_spaces=100,
        api_key=uuid.uuid4().hex,
    )
    return ParkingLot(**{**defaults, **kwargs})


async def test_create_parking_lot(db):
    lot = _make_lot()
    db.add(lot)
    await db.flush()

    result = await db.get(ParkingLot, lot.id)
    assert result.name == "테스트 주차장"
    assert result.base_fee == 0
    assert result.is_active is True


async def test_parking_lot_available_lte_total_constraint(db):
    """available_spaces > total_spaces 이면 DB 제약 위반."""
    lot = _make_lot(total_spaces=10, available_spaces=11)
    db.add(lot)
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_api_key_unique_constraint(db):
    """동일 api_key 는 중복 삽입 불가."""
    key = uuid.uuid4().hex
    db.add(_make_lot(api_key=key))
    await db.flush()

    db.add(_make_lot(api_key=key))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_vehicle_unique_per_lot(db):
    """같은 주차장에 동일 plate_hash 중복 입차 불가."""
    lot = _make_lot()
    db.add(lot)
    await db.flush()

    now = datetime.now(timezone.utc)
    db.add(Vehicle(parking_lot_id=lot.id, plate_hash="abc", plate_enc=b"enc", entered_at=now))
    await db.flush()

    db.add(Vehicle(parking_lot_id=lot.id, plate_hash="abc", plate_enc=b"enc", entered_at=now))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_entry_exit_log_invalid_event_type(db):
    """event_type 이 'entry' | 'exit' 외의 값이면 제약 위반."""
    lot = _make_lot()
    db.add(lot)
    await db.flush()

    now = datetime.now(timezone.utc)
    db.add(EntryExitLog(
        parking_lot_id=lot.id,
        plate_hash="abc",
        plate_enc=b"enc",
        event_type="wrong",  # 5자 이내지만 'entry'|'exit' 아님 → CHECK 위반
        client_timestamp=now,
        server_received_at=now,
    ))
    with pytest.raises(IntegrityError):
        await db.flush()
