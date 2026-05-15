import math
from datetime import datetime

from app.models.parking_lot import ParkingLot


def calculate_fee(lot: ParkingLot, entered_at: datetime, exited_at: datetime) -> int:
    duration_minutes = math.ceil((exited_at - entered_at).total_seconds() / 60)

    if duration_minutes <= lot.base_duration_minutes:
        fee = lot.base_fee
    else:
        over_minutes = duration_minutes - lot.base_duration_minutes
        fee = lot.base_fee + math.ceil(over_minutes / lot.extra_fee_unit_minutes) * lot.extra_fee_per_unit

    if lot.daily_max_fee is not None:
        days = math.floor((exited_at - entered_at).total_seconds() / 86400) + 1
        fee = min(fee, lot.daily_max_fee * days)

    return fee
