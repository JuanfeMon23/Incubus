"""Cierre de recepcion: examenes, preanaliticos unificados y numero de orden."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ValidationAppError
from app.modules.catalog_client.client import CatalogClient
from app.modules.orders.models import Order, OrderPrecondition, OrderSample, OrderTest
from app.modules.orders.order_number import (
    OrderNumberExhaustedError,
    format_order_number,
    year_month_key,
)
from app.modules.orders.preconditions import (
    EffectivePrecondition,
    dedupe_preconditions,
    slot_key,
)
from app.modules.orders.samples import group_samples
from app.modules.queue import service as queue_service
from app.modules.queue.models import Patient
from app.modules.queue.transitions import QueueStatus

# Datos minimos de la secretaria para cerrar la recepcion.
REQUIRED_PATIENT_FIELDS = ("sex", "birth_date", "address")


class OrderNumberExhausted(AppError):
    status_code = 409
    code = "order_number_exhausted"


async def next_order_number(session: AsyncSession, moment: datetime) -> str:
    """Consecutivo atomico del mes: sin duplicados ni huecos bajo concurrencia."""
    year, month = year_month_key(moment)
    key = f"{year % 100:02d}{month:02d}"
    result = await session.execute(
        text(
            "INSERT INTO order_counters (year_month, last_value) VALUES (:k, 1) "
            "ON CONFLICT (year_month) DO UPDATE "
            "SET last_value = order_counters.last_value + 1 "
            "RETURNING last_value"
        ),
        {"k": key},
    )
    try:
        return format_order_number(year, month, result.scalar_one())
    except OrderNumberExhaustedError as exc:
        raise OrderNumberExhausted(str(exc), {"year_month": key}) from exc


def _effective_preconditions(
    test: dict, categories: dict[str, str]
) -> list[EffectivePrecondition]:
    out = []
    for p in test.get("preconditions", []):
        if not p.get("is_active", True):
            continue
        out.append(
            EffectivePrecondition(
                category=categories.get(p["precondition_id"], "otro"),
                name=p["name"],
                duration_value=p.get("duration_value"),
                duration_unit=p.get("duration_unit"),
                patient_instructions=p.get("patient_instructions"),
            )
        )
    return out


async def resolve_tests(
    catalog: CatalogClient, test_codes: list[str]
) -> tuple[list[dict], list[dict]]:
    """Examenes del catalogo + preanaliticos unificados (con examenes origen)."""
    tests, missing = [], []
    for code in dict.fromkeys(test_codes):
        test = await catalog.get_test_by_code(code)
        (tests if test else missing).append(test or code)
    if missing:
        raise ValidationAppError(
            "Hay examenes que no existen o estan inactivos en el catalogo.",
            {"test_codes": missing},
        )
    categories = await catalog.precondition_categories() if tests else {}
    pairs: list[tuple[EffectivePrecondition, str]] = []
    for test in tests:
        for pre in _effective_preconditions(test, categories):
            pairs.append((pre, test["code"]))
    merged = dedupe_preconditions([p for p, _ in pairs])
    preconditions = [
        {
            "category": item.category,
            "name": item.name,
            "duration_value": item.duration_value,
            "duration_unit": item.duration_unit,
            "patient_instructions": item.patient_instructions,
            "source_test_codes": sorted(
                {code for pre, code in pairs if slot_key(pre) == slot_key(item)}
            ),
        }
        for item in merged
    ]
    return tests, preconditions


async def close_reception(
    session: AsyncSession,
    catalog: CatalogClient,
    entry_id: UUID,
    test_codes: list[str],
    actor: str | None,
) -> Order:
    entry = await queue_service.get_entry(session, entry_id, lock=True)
    if entry.status != QueueStatus.EN_ATENCION_RECEPCION:
        raise ValidationAppError(
            "Solo se cierra la recepcion de un paciente en atencion de recepcion.",
            {"status": entry.status},
        )
    if not test_codes:
        raise ValidationAppError(
            "La orden necesita al menos un examen.", {"test_codes": []}
        )
    patient = await session.get(Patient, entry.patient_id)
    missing = [f for f in REQUIRED_PATIENT_FIELDS if not getattr(patient, f)]
    if missing:
        raise ValidationAppError(
            "Faltan datos del paciente para cerrar la recepcion.",
            {"missing_fields": missing},
        )
    tests, preconditions = await resolve_tests(catalog, test_codes)
    order = Order(
        order_number=await next_order_number(session, datetime.now(UTC)),
        queue_entry_id=entry.id,
        patient_id=patient.id,
    )
    session.add(order)
    await session.flush()
    for test in tests:
        session.add(
            OrderTest(
                order_id=order.id,
                test_code=test["code"],
                test_name=test["name"],
                snapshot=test,
            )
        )
    for pre in preconditions:
        session.add(OrderPrecondition(order_id=order.id, **pre))
    await session.flush()
    await queue_service.change_status(
        session,
        entry.id,
        QueueStatus.EN_ESPERA_TOMA_MUESTRAS,
        actor=actor,
        note=f"orden {order.order_number}",
    )
    return order


async def ensure_samples(
    session: AsyncSession, catalog: CatalogClient, entry_id: UUID
) -> None:
    """Crea los tubos de la orden la primera vez que el paciente entra a toma de
    muestras (no al cerrar recepcion). Idempotente: devolver y volver a tomar al
    paciente no duplica tubos. Usa el snapshot de examenes de la orden."""
    order = (
        await session.execute(select(Order).where(Order.queue_entry_id == entry_id))
    ).scalar_one_or_none()
    if order is None:
        return
    existing = (
        await session.execute(
            select(OrderSample.id).where(OrderSample.order_id == order.id).limit(1)
        )
    ).first()
    if existing is not None:
        return
    snapshots = (
        await session.execute(
            select(OrderTest.snapshot).where(OrderTest.order_id == order.id)
        )
    ).scalars()
    tests = list(snapshots)
    sample_types = await catalog.sample_types_by_id() if tests else {}
    for tube in group_samples(tests, sample_types):
        session.add(
            OrderSample(
                order_id=order.id,
                sample_type_id=tube.sample_type_id,
                sample_type_code=tube.code,
                name=tube.name,
                cap_color_hex=tube.cap_color_hex,
                draw_order=tube.draw_order,
                collection_instructions=tube.collection_instructions,
                required_volume_ml=tube.required_volume_ml,
                test_codes=tube.test_codes,
            )
        )
    await session.flush()
