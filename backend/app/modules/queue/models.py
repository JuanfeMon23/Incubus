"""Cola de atencion: catalogos parametrizados, pacientes, entradas e historial."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db.base import Base
from app.core.db.mixins import CatalogMixin, Timestamps, UUIDv7PK
from app.modules.queue.transitions import QueueStatus

STATUS_VALUES = tuple(s.value for s in QueueStatus)
_STATUS_IN = ", ".join(f"'{v}'" for v in STATUS_VALUES)
KIND_VALUES = ("enter", "advance", "return", "remove")


class Priority(CatalogMixin, Base):
    """Prioridad parametrizada: nombre, color y rango (menor = mas urgente)."""

    __tablename__ = "priorities"

    color_hex: Mapped[str] = mapped_column(String(7), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("color_hex ~ '^#[0-9A-Fa-f]{6}$'", name="color_hex_format"),
    )


class RemovalReason(CatalogMixin, Base):
    __tablename__ = "removal_reasons"


class ReturnReason(CatalogMixin, Base):
    __tablename__ = "return_reasons"


class DocumentType(CatalogMixin, Base):
    """Tipo de documento de identidad parametrizado (CC, TI, CE, PA...)."""

    __tablename__ = "document_types"


class Patient(UUIDv7PK, Timestamps, Base):
    __tablename__ = "patients"

    document_type: Mapped[str] = mapped_column(
        String(8), server_default=text("'CC'"), nullable=False
    )
    document_number: Mapped[str] = mapped_column(String(20), nullable=False)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    second_name: Mapped[str | None] = mapped_column(String(80))
    first_last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    second_last_name: Mapped[str | None] = mapped_column(String(80))
    sex: Mapped[str | None] = mapped_column(String(1))
    birth_date: Mapped[date | None] = mapped_column(Date)
    birth_place: Mapped[str | None] = mapped_column(String(120))
    blood_type: Mapped[str | None] = mapped_column(String(3))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(String(255))
    insurer: Mapped[str | None] = mapped_column(String(150))

    __table_args__ = (
        Index(
            "uq_patients_document",
            "document_type",
            "document_number",
            unique=True,
        ),
        CheckConstraint("sex IN ('M', 'F')", name="sex_values"),
    )


class QueueEntry(UUIDv7PK, Timestamps, Base):
    __tablename__ = "queue_entries"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False
    )
    priority_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("priorities.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), server_default=text("'pre_recepcion'"), nullable=False
    )
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    assigned_professional_id: Mapped[str | None] = mapped_column(String(64))
    assigned_professional_name: Mapped[str | None] = mapped_column(String(150))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Borrador de recepcion: sobrevive a una devolucion a pre-recepcion.
    draft: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    arrived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_IN})", name="status_values"),
        # Un paciente no puede estar dos veces en la cola a la vez.
        Index(
            "uq_queue_entries_active_patient",
            "patient_id",
            unique=True,
            postgresql_where=text("status <> 'retirado'"),
        ),
        Index("ix_queue_entries_status_priority", "status", "priority_id"),
    )


class QueueStatusHistory(UUIDv7PK, Base):
    """Historial append-only de cada cambio de estado (fuente de analitica).

    `changed_at` lo asigna la BD; un trigger impide UPDATE y DELETE.
    """

    __tablename__ = "queue_status_history"

    queue_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queue_entries.id"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    actor: Mapped[str | None] = mapped_column(String(120))
    priority_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("priorities.id"), nullable=False
    )
    removal_reason_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("removal_reasons.id")
    )
    return_reason_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("return_reasons.id")
    )
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(f"to_status IN ({_STATUS_IN})", name="to_status_values"),
        CheckConstraint(
            "kind IN ('enter', 'advance', 'return', 'remove')", name="kind_values"
        ),
        Index("ix_queue_status_history_entry", "queue_entry_id", "changed_at"),
        Index("ix_queue_status_history_status", "to_status", "changed_at"),
    )
