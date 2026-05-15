import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LogOut(BaseModel):
    id: uuid.UUID
    parking_lot_id: uuid.UUID
    plate: str          # plate_enc를 복호화한 번호판 원문
    event_type: str
    fee: Optional[int]
    client_timestamp: datetime
    server_received_at: datetime
