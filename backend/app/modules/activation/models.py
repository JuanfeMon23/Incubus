"""Codigo de activacion de un solo uso para vincular a un paciente en Acuarius."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base
from app.core.db.mixins import UUIDv7PK


class ActivationCode(UUIDv7PK, Base):
    """Un codigo por orden. Solo se guarda su HMAC-SHA256 (hex); el codigo en
    claro se entrega una vez al emitirlo y no se puede recuperar."""

    __tablename__ = "activation_codes"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), unique=True, nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("char_length(code_hash) = 64", name="hash_length"),
        CheckConstraint("expires_at > created_at", name="expires_after_creation"),
    )
