import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    parking_lot_id: uuid.UUID


class UserPatch(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    role: str
    parking_lot_id: Optional[uuid.UUID]
    created_at: datetime

    model_config = {"from_attributes": True}
