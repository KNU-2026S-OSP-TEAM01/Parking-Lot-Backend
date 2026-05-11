import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id:             Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username:       Mapped[str]              = mapped_column(String(50), unique=True, nullable=False)
    email:          Mapped[str]              = mapped_column(String(100), unique=True, nullable=False)
    password_hash:  Mapped[str]              = mapped_column(String(255), nullable=False)
    role:           Mapped[str]              = mapped_column(String(20), nullable=False, default="admin")
    parking_lot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("parking_lots.id", ondelete="SET NULL"))
    created_at:     Mapped[datetime]         = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('superadmin', 'admin')", name="ck_user_role"),
    )
