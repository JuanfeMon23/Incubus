"""Ordenes de laboratorio: numero, examenes y preanaliticos con snapshot."""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.mixins import Timestamps, UUIDv7PK


class OrderCounter(Base):
    """Consecutivo por mes (`AAMM`), incrementado de forma atomica."""

    __tablename__ = "order_counters"

    year_month: Mapped[str] = mapped_column(String(4), primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class Order(UUIDv7PK, Timestamps, Base):
    __tablename__ = "orders"

    order_number: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    queue_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queue_entries.id"),
        unique=True,
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False
    )


class OrderTest(UUIDv7PK, Base):
    """Examen de la orden con snapshot de lo que Vladimir devolvio al cerrar."""

    __tablename__ = "order_tests"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    test_code: Mapped[str] = mapped_column(String(64), nullable=False)
    test_name: Mapped[str] = mapped_column(String(150), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)


class OrderPrecondition(UUIDv7PK, Base):
    """Preanalitico ya unificado que se le indica al paciente."""

    __tablename__ = "order_preconditions"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    duration_value: Mapped[float | None] = mapped_column(Float)
    duration_unit: Mapped[str | None] = mapped_column(String(16))
    patient_instructions: Mapped[str | None] = mapped_column(Text)
    source_test_codes: Mapped[list] = mapped_column(JSONB, nullable=False)
