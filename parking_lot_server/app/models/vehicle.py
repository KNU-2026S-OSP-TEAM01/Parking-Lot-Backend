import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parking_lot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("parking_lots.id", ondelete="CASCADE"), nullable=False)
    plate_hash:     Mapped[str]       = mapped_column(String(64), nullable=False)
    plate_enc:      Mapped[bytes]     = mapped_column(LargeBinary, nullable=False)
    entered_at:     Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("parking_lot_id", "plate_hash", name="uq_vehicle_lot_plate"),
        Index("idx_vehicles_lookup", "parking_lot_id", "plate_hash"),
    )
