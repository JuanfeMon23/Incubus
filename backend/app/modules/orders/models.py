"""Ordenes de laboratorio: numero, examenes y preanaliticos con snapshot."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
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
    # Area que valida el examen y estado de su validacion (pending|draft|validated).
    area_id: Mapped[str | None] = mapped_column(String(64))
    area_code: Mapped[str | None] = mapped_column(String(64))
    validation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_by_id: Mapped[str | None] = mapped_column(String(64))
    validated_by_name: Mapped[str | None] = mapped_column(String(150))


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
    key: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    reception_met: Mapped[bool | None] = mapped_column(Boolean)
    reception_note: Mapped[str | None] = mapped_column(Text)
    reception_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    reception_checked_by: Mapped[str | None] = mapped_column(String(120))
    sampling_met: Mapped[bool | None] = mapped_column(Boolean)
    sampling_note: Mapped[str | None] = mapped_column(Text)
    sampling_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    sampling_checked_by: Mapped[str | None] = mapped_column(String(120))


class OrderSample(UUIDv7PK, Base):
    """Tubo de la orden: un tipo de muestra compartido por varios examenes."""

    __tablename__ = "order_samples"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    sample_type_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    cap_color_hex: Mapped[str | None] = mapped_column(String(7))
    draw_order: Mapped[int | None] = mapped_column(Integer)
    collection_instructions: Mapped[str | None] = mapped_column(Text)
    required_volume_ml: Mapped[float | None] = mapped_column(Float)
    test_codes: Mapped[list] = mapped_column(JSONB, nullable=False)
    area_route: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    labels_printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_by: Mapped[str | None] = mapped_column(String(120))
    # Recepcion de la muestra en el laboratorio (check de entrada).
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by: Mapped[str | None] = mapped_column(String(120))


class OrderResult(UUIDv7PK, Base):
    """Un analito de un examen de la orden: estructura de la plantilla (snapshot)
    y el valor digitado por el profesional."""

    __tablename__ = "order_results"

    order_test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("order_tests.id"), nullable=False
    )
    analyte_code: Mapped[str] = mapped_column(String(64), nullable=False)
    analyte_name: Mapped[str] = mapped_column(String(150), nullable=False)
    section_name: Mapped[str | None] = mapped_column(String(150))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    result_type: Mapped[str] = mapped_column(String(24), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    decimals: Mapped[int | None] = mapped_column(Integer)
    options: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    formula: Mapped[str | None] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    is_reportable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    ranges: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    value: Mapped[dict | None] = mapped_column(JSONB)  # {"v": <valor tipado>}
    flag: Mapped[str | None] = mapped_column(String(16))
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entered_by: Mapped[str | None] = mapped_column(String(120))

    __table_args__ = (
        UniqueConstraint("order_test_id", "analyte_code", name="analyte_per_test"),
    )
