import uuid
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ParkingLot(Base):
    __tablename__ = "parking_lots"

    id:                     Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id:          Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name:                   Mapped[str]        = mapped_column(String(100), nullable=False)
    address:                Mapped[str | None] = mapped_column(String(255))
    total_spaces:           Mapped[int]        = mapped_column(Integer, nullable=False)
    available_spaces:       Mapped[int]        = mapped_column(Integer, nullable=False)
    base_fee:               Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    base_duration_minutes:  Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    extra_fee_per_unit:     Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    extra_fee_unit_minutes: Mapped[int]        = mapped_column(Integer, nullable=False, default=10)
    daily_max_fee:          Mapped[int | None] = mapped_column(Integer)
    api_key:                Mapped[str]        = mapped_column(String(64), unique=True, nullable=False)
    is_active:              Mapped[bool]       = mapped_column(Boolean, nullable=False, default=True)
    created_at:             Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at:             Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("total_spaces > 0",                 name="ck_total_spaces_positive"),
        CheckConstraint("available_spaces >= 0",            name="ck_available_spaces_non_negative"),
        CheckConstraint("available_spaces <= total_spaces", name="ck_available_lte_total"),
    )
