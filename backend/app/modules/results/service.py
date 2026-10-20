"""Recepcion en laboratorio y validacion de resultados por area."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.modules.catalog_client.client import CatalogClient
from app.modules.orders.models import Order, OrderResult, OrderSample, OrderTest
from app.modules.queue import service as queue_service
from app.modules.queue.models import Patient, QueueEntry
from app.modules.queue.transitions import QueueStatus
from app.modules.results.flags import (
    age_in_years,
    evaluate_flag,
    pick_range,
    reference_text,
)
from app.modules.results.formula import FormulaError, evaluate_formula
from app.modules.results.values import ResultValueError, normalize_value


class MissingResultsError(ValidationAppError):
    code = "missing_results"


class InvalidResultError(ValidationAppError):
    code = "invalid_result"


# ------------------------------------------------------------------ acceso


async def professional_area_ids(
    catalog: CatalogClient, professional_id: str
) -> set[str]:
    areas = await catalog.areas_with_managers()
    return {a["id"] for a in areas if a.get("manager_staff_id") == professional_id}


async def _load_test(
    session: AsyncSession,
    catalog: CatalogClient,
    order_test_id: UUID,
    professional_id: str,
) -> tuple[OrderTest, Order]:
    test = await session.get(OrderTest, order_test_id)
    if test is None:
        raise NotFoundError(
            f"No existe el examen de orden '{order_test_id}'.",
            {"id": str(order_test_id)},
        )
    areas = await professional_area_ids(catalog, professional_id)
    if not test.area_id or test.area_id not in areas:
        raise ForbiddenError(
            "El examen pertenece a un area que no tienes asignada.",
            {"area_code": test.area_code},
        )
    order = await session.get(Order, test.order_id)
    return test, order


# --------------------------------------------------------- estructura


async def ensure_structure(
    session: AsyncSession, catalog: CatalogClient, test: OrderTest
) -> list[OrderResult]:
    rows = list(
        (
            await session.execute(
                select(OrderResult)
                .where(OrderResult.order_test_id == test.id)
                .order_by(OrderResult.sort_order)
            )
        ).scalars()
    )
    if rows:
        return rows
    version_id = (test.snapshot or {}).get("result_template_version_id")
    if not version_id:
        raise ValidationAppError(
            "El examen no tiene una plantilla de resultados asignada.",
            {"test_code": test.test_code},
        )
    structure = await catalog.template_structure(str(version_id))
    for a in structure["analytes"]:
        session.add(
            OrderResult(
                order_test_id=test.id,
                analyte_code=a["code"],
                analyte_name=a["name"],
                section_name=a.get("section"),
                sort_order=a["sort_order"],
                result_type=a["result_type"],
                unit=a.get("unit"),
                decimals=a.get("decimals"),
                options=a.get("options", []),
                formula=a.get("formula"),
                is_required=a.get("is_required", True),
                is_reportable=a.get("is_reportable", True),
                ranges=a.get("ranges", []),
            )
        )
    await session.flush()
    return await ensure_structure(session, catalog, test)


def _patient_context(patient: Patient) -> dict:
    age = age_in_years(patient.birth_date)
    return {
        "name": " ".join(
            filter(
                None,
                [
                    patient.first_name,
                    patient.second_name,
                    patient.first_last_name,
                    patient.second_last_name,
                ],
            )
        ),
        "document_type": patient.document_type,
        "document_number": patient.document_number,
        "sex": patient.sex,
        "age_years": round(age, 1) if age is not None else None,
    }


def _row_dict(row: OrderResult, patient: Patient) -> dict:
    rng = pick_range(row.ranges, patient.sex, age_in_years(patient.birth_date))
    value = (row.value or {}).get("v")
    return {
        "code": row.analyte_code,
        "name": row.analyte_name,
        "section": row.section_name,
        "result_type": row.result_type,
        "unit": row.unit,
        "decimals": row.decimals,
        "options": row.options,
        "formula": row.formula,
        "is_required": row.is_required,
        "is_reportable": row.is_reportable,
        "reference": reference_text(rng),
        "range": (
            {k: rng.get(k) for k in ("low", "high", "critical_low", "critical_high")}
            if rng
            else None
        ),
        "value": value,
        "flag": row.flag,
    }


async def test_detail(
    session: AsyncSession,
    catalog: CatalogClient,
    order_test_id: UUID,
    professional_id: str,
) -> dict:
    test, order = await _load_test(session, catalog, order_test_id, professional_id)
    rows = await ensure_structure(session, catalog, test)
    patient = await session.get(Patient, order.patient_id)
    return {
        "order_test_id": str(test.id),
        "order_number": order.order_number,
        "code": test.test_code,
        "name": test.test_name,
        "area_code": test.area_code,
        "validation_status": test.validation_status,
        "validated_by": test.validated_by_name,
        "patient": _patient_context(patient),
        "results": [_row_dict(r, patient) for r in rows],
    }


# ----------------------------------------------------------- valores


def _apply_values(
    rows: list[OrderResult], values: dict, patient: Patient, actor: str
) -> None:
    by_code = {r.analyte_code: r for r in rows}
    unknown = [c for c in values if c not in by_code]
    if unknown:
        raise InvalidResultError("Analito desconocido.", {"field": unknown[0]})
    now = datetime.now(UTC)
    for code, raw in values.items():
        row = by_code[code]
        if row.result_type == "calculated":
            raise InvalidResultError(
                "Un analito calculado no se digita; se obtiene de su formula.",
                {"field": code},
            )
        try:
            typed = normalize_value(
                row.result_type, raw, decimals=row.decimals, options=row.options
            )
        except ResultValueError as exc:
            raise InvalidResultError(str(exc), {"field": code}) from exc
        row.value = None if typed is None else {"v": typed}
        row.entered_at = now if typed is not None else None
        row.entered_by = actor if typed is not None else None

    # calculados a partir de los valores numericos actuales
    numeric = {
        r.analyte_code: float((r.value or {})["v"])
        for r in rows
        if r.value is not None
        and isinstance(r.value.get("v"), (int, float))
        and not isinstance(r.value.get("v"), bool)
    }
    for row in rows:
        if row.result_type != "calculated" or not row.formula:
            continue
        try:
            computed = evaluate_formula(row.formula, numeric)
        except FormulaError:
            computed = None
        if computed is None:
            row.value, row.entered_at, row.entered_by = None, None, None
        else:
            if row.decimals is not None:
                computed = round(computed, row.decimals)
            row.value = {"v": computed}
            row.entered_at, row.entered_by = now, actor
            numeric[row.analyte_code] = computed

    age = age_in_years(patient.birth_date)
    for row in rows:
        value = (row.value or {}).get("v")
        rng = pick_range(row.ranges, patient.sex, age)
        row.flag = evaluate_flag(value, rng) if value is not None else None


async def save_values(
    session: AsyncSession,
    catalog: CatalogClient,
    order_test_id: UUID,
    professional_id: str,
    professional_name: str,
    values: dict,
) -> dict:
    test, order = await _load_test(session, catalog, order_test_id, professional_id)
    if test.validation_status == "validated":
        raise ConflictError(
            "El examen ya fue validado y no se puede modificar.",
            {"code": test.test_code},
        )
    rows = await ensure_structure(session, catalog, test)
    patient = await session.get(Patient, order.patient_id)
    _apply_values(rows, values, patient, professional_name)
    test.validation_status = (
        "draft" if any(r.value is not None for r in rows) else "pending"
    )
    await session.flush()
    return await test_detail(session, catalog, order_test_id, professional_id)


async def validate_test(
    session: AsyncSession,
    catalog: CatalogClient,
    order_test_id: UUID,
    professional_id: str,
    professional_name: str,
    values: dict,
) -> tuple[dict, bool]:
    """Valida el examen; devuelve su detalle y si la orden quedo finalizada."""
    # Bloquea la entrada ANTES de guardar y contar pendientes: dos validaciones
    # de los ultimos examenes se serializan y la segunda ve a la primera.
    locked = await session.get(OrderTest, order_test_id)
    if locked is not None:
        parent = await session.get(Order, locked.order_id)
        await queue_service.get_entry(session, parent.queue_entry_id, lock=True)
        await session.refresh(locked)
    await save_values(
        session, catalog, order_test_id, professional_id, professional_name, values
    )
    test = await session.get(OrderTest, order_test_id)
    rows = await ensure_structure(session, catalog, test)
    # un calculado se obtiene de sus insumos: si faltan, se reportan ellos
    missing = [
        r.analyte_code
        for r in rows
        if r.is_required and r.value is None and r.result_type != "calculated"
    ]
    if missing:
        raise MissingResultsError(
            "Faltan resultados obligatorios para validar el examen.", {"codes": missing}
        )
    test.validation_status = "validated"
    test.validated_at = datetime.now(UTC)
    test.validated_by_id = professional_id
    test.validated_by_name = professional_name
    await session.flush()

    order = await session.get(Order, test.order_id)
    pending = (
        await session.execute(
            select(OrderTest.id).where(
                OrderTest.order_id == order.id,
                OrderTest.validation_status != "validated",
            )
        )
    ).first()
    finalized = pending is None
    if finalized:
        await queue_service.change_status(
            session,
            order.queue_entry_id,
            QueueStatus.FINALIZADA,
            actor=professional_name,
            note=f"orden {order.order_number} validada",
        )
    detail = await test_detail(session, catalog, order_test_id, professional_id)
    return detail, finalized


# ---------------------------------------------------------------- orden


async def order_for_professional(
    session: AsyncSession, catalog: CatalogClient, entry_id: UUID, professional_id: str
) -> dict:
    """Examenes de la orden que corresponden a las areas del profesional,
    incluidos los ya validados (se muestran como completados)."""
    areas = await professional_area_ids(catalog, professional_id)
    row = (
        await session.execute(
            select(Order, Patient)
            .join(Patient, Patient.id == Order.patient_id)
            .where(Order.queue_entry_id == entry_id)
        )
    ).first()
    if row is None:
        raise NotFoundError(
            f"La entrada '{entry_id}' no tiene orden.",
            {"queue_entry_id": str(entry_id)},
        )
    order, patient = row
    tests = list(
        (
            await session.execute(
                select(OrderTest)
                .where(
                    OrderTest.order_id == order.id, OrderTest.area_id.in_(areas or {""})
                )
                .order_by(OrderTest.test_code)
            )
        ).scalars()
    )
    if not tests:
        raise ForbiddenError(
            "La orden no tiene examenes de las areas que tienes asignadas.",
            {"order_number": order.order_number},
        )
    return {
        "entry_id": str(entry_id),
        "order_number": order.order_number,
        "patient": _patient_context(patient),
        "tests": [
            {
                "order_test_id": str(t.id),
                "code": t.test_code,
                "name": t.test_name,
                "area_code": t.area_code,
                "validation_status": t.validation_status,
                "validated_by": t.validated_by_name,
                "validated_at": t.validated_at.isoformat() if t.validated_at else None,
            }
            for t in tests
        ],
    }


# ---------------------------------------------------------------- colas


def _matches(q: str, *texts: str | None) -> bool:
    needle = q.casefold()
    return any(needle in (t or "").casefold() for t in texts)


async def results_queue(
    session: AsyncSession,
    catalog: CatalogClient,
    professional_id: str,
    q: str | None,
) -> list[dict]:
    areas = await professional_area_ids(catalog, professional_id)
    if not areas:
        return []
    stmt = (
        select(QueueEntry, Order, Patient)
        .join(Order, Order.queue_entry_id == QueueEntry.id)
        .join(Patient, Patient.id == QueueEntry.patient_id)
        .where(QueueEntry.status == QueueStatus.EN_LABORATORIO.value)
        .order_by(QueueEntry.arrived_at)
    )
    out = []
    for entry, order, patient in (await session.execute(stmt)).all():
        tests = list(
            (
                await session.execute(
                    select(OrderTest).where(
                        OrderTest.order_id == order.id,
                        OrderTest.area_id.in_(areas),
                        OrderTest.validation_status != "validated",
                    )
                )
            ).scalars()
        )
        if not tests:
            continue
        ctx = _patient_context(patient)
        if q and not (
            _matches(
                q,
                order.order_number,
                ctx["name"],
                ctx["document_number"],
                *[t.test_code for t in tests],
                *[t.test_name for t in tests],
            )
        ):
            continue
        out.append(
            {
                "entry_id": str(entry.id),
                "order_number": order.order_number,
                "patient_name": ctx["name"],
                "document": f"{ctx['document_type']} {ctx['document_number']}",
                "tests": [
                    {
                        "order_test_id": str(t.id),
                        "code": t.test_code,
                        "name": t.test_name,
                        "area_code": t.area_code,
                        "validation_status": t.validation_status,
                    }
                    for t in tests
                ],
            }
        )
    return out


async def lab_reception_queue(session: AsyncSession, q: str | None) -> list[dict]:
    stmt = (
        select(QueueEntry, Order, Patient)
        .join(Order, Order.queue_entry_id == QueueEntry.id)
        .join(Patient, Patient.id == QueueEntry.patient_id)
        .where(QueueEntry.status == QueueStatus.TOMA_FINALIZADA.value)
        .order_by(QueueEntry.arrived_at)
    )
    out = []
    for entry, order, patient in (await session.execute(stmt)).all():
        ctx = _patient_context(patient)
        if q and not _matches(
            q, order.order_number, ctx["name"], ctx["document_number"]
        ):
            continue
        samples = list(
            (
                await session.execute(
                    select(OrderSample)
                    .where(OrderSample.order_id == order.id)
                    .order_by(OrderSample.draw_order.nulls_last(), OrderSample.name)
                )
            ).scalars()
        )
        out.append(
            {
                "entry_id": str(entry.id),
                "order_number": order.order_number,
                "patient_name": ctx["name"],
                "document": f"{ctx['document_type']} {ctx['document_number']}",
                "pending": sum(1 for s in samples if s.received_at is None),
                "samples": [
                    {
                        "id": str(s.id),
                        "name": s.name,
                        "cap_color_hex": s.cap_color_hex,
                        "test_codes": s.test_codes,
                        "area_route": s.area_route,
                        "received_at": s.received_at.isoformat()
                        if s.received_at
                        else None,
                        "received_by": s.received_by,
                    }
                    for s in samples
                ],
            }
        )
    return out


async def set_received(
    session: AsyncSession, sample_id: UUID, actor: str | None, received: bool
) -> tuple[OrderSample, str]:
    sample = await session.get(OrderSample, sample_id)
    if sample is None:
        raise NotFoundError(
            f"No existe la muestra '{sample_id}'.", {"id": str(sample_id)}
        )
    order = await session.get(Order, sample.order_id)
    entry = await queue_service.get_entry(session, order.queue_entry_id, lock=True)
    if entry.status != QueueStatus.TOMA_FINALIZADA.value:
        raise ConflictError(
            "La orden no esta esperando recepcion en laboratorio.",
            {"status": entry.status},
        )
    await session.refresh(
        sample
    )  # puede haber cambiado mientras se esperaba el bloqueo
    sample.received_at = datetime.now(UTC) if received else None
    sample.received_by = actor if received else None
    await session.flush()
    await queue_service.touch_entry(session, entry.id)
    status = entry.status
    if received:
        pending = (
            await session.execute(
                select(OrderSample.id).where(
                    OrderSample.order_id == order.id, OrderSample.received_at.is_(None)
                )
            )
        ).first()
        if pending is None:
            moved = await queue_service.change_status(
                session,
                entry.id,
                QueueStatus.EN_LABORATORIO,
                actor=actor,
                note=f"orden {order.order_number} recibida en laboratorio",
            )
            status = moved.status
    return sample, status
