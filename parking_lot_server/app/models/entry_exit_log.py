import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class EntryExitLog(Base):
    __tablename__ = "entry_exit_logs"

    id:                 Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parking_lot_id:     Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), ForeignKey("parking_lots.id"), nullable=False)
    plate_hash:         Mapped[str]        = mapped_column(String(64), nullable=False)
    plate_enc:          Mapped[bytes]      = mapped_column(LargeBinary, nullable=False)
    event_type:         Mapped[str]        = mapped_column(String(5), nullable=False)
    fee:                Mapped[int | None] = mapped_column(Integer)
    client_timestamp:   Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False)
    server_received_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("event_type IN ('entry', 'exit', 'admin')", name="ck_event_type"),
        Index("idx_logs_lot_time", "parking_lot_id", "client_timestamp"),
    )
