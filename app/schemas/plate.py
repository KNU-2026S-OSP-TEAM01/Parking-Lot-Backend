from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PlateRequest(BaseModel):
    plate: str
    timestamp: datetime


class EntryResponse(BaseModel):
    event: Literal["entry"]
    entered_at: datetime


class ExitResponse(BaseModel):
    event: Literal["exit"]
    fee: int
    parked_duration_minutes: int
