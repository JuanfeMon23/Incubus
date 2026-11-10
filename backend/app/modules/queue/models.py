"""Cola de atencion: catalogos parametrizados, pacientes, entradas e historial."""

import uuid
from datetime import date, datetime
from typing import ClassVar

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    FetchedValue,
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
from app.core.db.mixins import CatalogMixin, SortedCatalogMixin, Timestamps, UUIDv7PK


class Priority(CatalogMixin, Base):
    """Prioridad parametrizada: nombre, color y rango (menor = mas urgente)."""

    __tablename__ = "priorities"

    color_hex: Mapped[str] = mapped_column(String(7), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    # La que preselecciona el ingreso; solo una (indice unico parcial).
    is_default: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )

    __table_args__ = (
        CheckConstraint("color_hex ~ '^#[0-9A-Fa-f]{6}$'", name="color_hex_format"),
        Index(
            "uq_priorities_single_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )


class RemovalReason(CatalogMixin, Base):
    __tablename__ = "removal_reasons"


class ReturnReason(CatalogMixin, Base):
    __tablename__ = "return_reasons"


class BloodType(SortedCatalogMixin, Base):
    """Grupo sanguineo y RH (`code` = 'A+', 'O-'...). Propio de Incubus."""

    __tablename__ = "blood_types"


class QueueStatusCatalog(SortedCatalogMixin, Base):
    """Estado/etapa de la cola: nombre y orden de presentacion. Los `code` son de
    sistema (`QueueStatus`); `is_terminal` marca los que sacan al paciente de la cola."""

    __tablename__ = "queue_statuses"

    is_terminal: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )


class QueueTransitionKind(SortedCatalogMixin, Base):
    """Tipo de cambio de estado del historial: enter, advance, return, remove."""

    __tablename__ = "queue_transition_kinds"


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
    # Codigo del catalogo de sexos de Vladimir (`male`/`female`): sin FK, el
    # backend valida contra su API.
    sex: Mapped[str | None] = mapped_column(String(16))
    birth_date: Mapped[date | None] = mapped_column(Date)
    birth_place: Mapped[str | None] = mapped_column(String(120))
    blood_type: Mapped[str | None] = mapped_column(
        String(3), ForeignKey("blood_types.code"), index=True
    )
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
        String(32),
        ForeignKey("queue_statuses.code"),
        server_default=text("'pre_recepcion'"),
        nullable=False,
    )
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    claimed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
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
    # Version monotona: la incrementa el trigger `trg_queue_entries_bump_version`
    # en cada UPDATE (la app nunca la escribe). `eager_defaults` la trae de vuelta
    # con RETURNING tras el flush.
    version: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        server_onupdate=FetchedValue(),
        nullable=False,
    )

    __mapper_args__: ClassVar[dict] = {"eager_defaults": True}

    __table_args__ = (
        # Un paciente no puede estar dos veces en la cola a la vez (un turno
        # retirado o finalizado ya no cuenta como activo).
        Index(
            "uq_queue_entries_active_patient",
            "patient_id",
            unique=True,
            postgresql_where=text("status NOT IN ('retirado', 'finalizada')"),
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
    from_status: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("queue_statuses.code"), index=True
    )
    to_status: Mapped[str] = mapped_column(
        String(32), ForeignKey("queue_statuses.code"), nullable=False
    )
    kind: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("queue_transition_kinds.code"),
        nullable=False,
        index=True,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    actor: Mapped[str | None] = mapped_column(String(120))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
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
        Index("ix_queue_status_history_entry", "queue_entry_id", "changed_at"),
        Index("ix_queue_status_history_status", "to_status", "changed_at"),
        Index(
            "ix_queue_status_history_actor_user_id_changed_at",
            "actor_user_id",
            "changed_at",
        ),
    )
