import uuid
from datetime import datetime

from pydantic import BaseModel


class VehicleOut(BaseModel):
    id: uuid.UUID
    parking_lot_id: uuid.UUID
    plate: str          # plate_enc를 복호화한 번호판 원문
    entered_at: datetime
