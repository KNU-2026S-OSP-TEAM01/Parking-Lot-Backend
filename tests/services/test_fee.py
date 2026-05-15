from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.services.fee import calculate_fee


def make_lot(base_fee=0, base_min=0, extra_fee=0, extra_min=10, daily_max=None):
    lot = MagicMock()
    lot.base_fee = base_fee
    lot.base_duration_minutes = base_min
    lot.extra_fee_per_unit = extra_fee
    lot.extra_fee_unit_minutes = extra_min
    lot.daily_max_fee = daily_max
    return lot


def at(base: datetime, minutes: int) -> datetime:
    return base + timedelta(minutes=minutes)


BASE = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)


# ── 기본 요금 구간 ─────────────────────────────────────────────────────────────

def test_within_base_duration_returns_base_fee():
    lot = make_lot(base_fee=1000, base_min=30)
    assert calculate_fee(lot, BASE, at(BASE, 20)) == 1000


def test_exactly_base_duration_returns_base_fee():
    lot = make_lot(base_fee=1000, base_min=30)
    assert calculate_fee(lot, BASE, at(BASE, 30)) == 1000


# ── 추가 요금 구간 ─────────────────────────────────────────────────────────────

def test_one_extra_unit_adds_extra_fee():
    """기본 30분 이후 10분 단위 추가 요금."""
    lot = make_lot(base_fee=1000, base_min=30, extra_fee=200, extra_min=10)
    assert calculate_fee(lot, BASE, at(BASE, 40)) == 1200


def test_extra_unit_rounds_up():
    """초과 시간이 단위에 딱 맞지 않으면 올림 처리."""
    lot = make_lot(base_fee=1000, base_min=30, extra_fee=200, extra_min=10)
    # 31분 = 기본 초과 1분 → ceil(1/10) = 1단위 → 1200원
    assert calculate_fee(lot, BASE, at(BASE, 31)) == 1200


def test_multiple_extra_units():
    lot = make_lot(base_fee=1000, base_min=30, extra_fee=200, extra_min=10)
    # 50분 = 초과 20분 → 2단위 → 1000 + 400 = 1400
    assert calculate_fee(lot, BASE, at(BASE, 50)) == 1400


def test_free_parking_returns_zero():
    lot = make_lot(base_fee=0, base_min=0, extra_fee=0, extra_min=10)
    assert calculate_fee(lot, BASE, at(BASE, 120)) == 0


# ── daily_max_fee ─────────────────────────────────────────────────────────────

def test_daily_max_caps_fee():
    lot = make_lot(base_fee=1000, base_min=30, extra_fee=200, extra_min=10, daily_max=1200)
    # 계산상 1400원이지만 상한 1200원
    assert calculate_fee(lot, BASE, at(BASE, 50)) == 1200


def test_daily_max_none_no_cap():
    lot = make_lot(base_fee=1000, base_min=30, extra_fee=200, extra_min=10, daily_max=None)
    assert calculate_fee(lot, BASE, at(BASE, 50)) == 1400


def test_daily_max_accumulates_per_24h():
    """입차 기준 25시간 → 적용 일수 2 → 상한 = daily_max × 2."""
    lot = make_lot(base_fee=0, base_min=0, extra_fee=1000, extra_min=1, daily_max=5000)
    # 25시간(1500분) → 계산상 1500 × 1000 = 1,500,000원
    # 적용 일수 = floor(25*3600 / 86400) + 1 = 2 → 상한 = 10,000원
    assert calculate_fee(lot, BASE, at(BASE, 25 * 60)) == 10000
