import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LotCreate(BaseModel):
    name: str
    address: str
    total_spaces: int = Field(gt=0)
    base_fee: int = 0
    base_duration_minutes: int = 0
    extra_fee_per_unit: int = 0
    extra_fee_unit_minutes: int = Field(default=10, gt=0)
    daily_max_fee: Optional[int] = None


class LotPatch(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    total_spaces: Optional[int] = Field(default=None, gt=0)
    base_fee: Optional[int] = None
    base_duration_minutes: Optional[int] = None
    extra_fee_per_unit: Optional[int] = None
    extra_fee_unit_minutes: Optional[int] = Field(default=None, gt=0)
    daily_max_fee: Optional[int] = None


class LotOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    name: str
    address: str
    total_spaces: int
    available_spaces: int
    base_fee: int
    base_duration_minutes: int
    extra_fee_per_unit: int
    extra_fee_unit_minutes: int
    daily_max_fee: Optional[int]
    latitude: float
    longitude: float
    api_key: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
