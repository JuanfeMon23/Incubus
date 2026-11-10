"""Linea de tiempo de una prueba: eventos reales + eventos derivados.

Reales: filas de `order_test_events` de la prueba, de la orden (scope `order`)
y de sus tubos (scope `sample`). Derivados: los que se reconstruyen de columnas
que ya existian (`queue_status_history`, tubos, preanaliticos, resultados,
validacion, codigo de activacion) para que las ordenes anteriores a la 0011
tambien tengan traza.

Criterio anti-duplicado: un derivado se omite si hay un evento real con el
mismo `step` (o su equivalente: `result.entered` ~ `result.changed`), una marca
de tiempo a menos de `TOLERANCE` (2 s) y las mismas llaves de identidad
(`sample_id`, `analyte_code`, `stage`) cuando el derivado las tiene. Los
cambios de estado de la cola usan pasos `queue.*` propios (son informacion
distinta de los eventos de la prueba); solo `order.finalized` coincide con un
evento real.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import runtime_settings
from app.core.leo import uuid_str
from app.core.trace import as_uuid
from app.modules.activation.models import ActivationCode
from app.modules.catalogs import service as catalogs_service
from app.modules.orders.models import (
    Order,
    OrderPrecondition,
    OrderResult,
    OrderSample,
    OrderTest,
    OrderTestEvent,
)
from app.modules.queue.models import QueueStatusHistory

# Tolerancia por defecto; la vigente sale de Ajustes (`trace.dedup_tolerance_seconds`).
TOLERANCE = timedelta(seconds=2)
MATCH_KEYS = ("sample_id", "analyte_code", "stage")
EQUIVALENT = {"result.entered": {"result.entered", "result.changed"}}

# Estado destino de la cola -> paso derivado.
_STATUS_STEP = {
    "pre_recepcion": "queue.entered",
    "en_atencion_recepcion": "queue.reception_claimed",
    "en_espera_impresion": "queue.reception_closed",
    "en_espera_toma_muestras": "queue.labels_printed",
    "en_atencion_toma_muestras": "queue.sampling_claimed",
    "toma_finalizada": "queue.sampling_finished",
    "en_laboratorio": "queue.in_laboratory",
    "finalizada": "order.finalized",
    "retirado": "queue.removed",
}


def _actor(
    user_id: UUID | None, name: str | None, staff_id: UUID | None = None
) -> dict:
    return {"id": uuid_str(user_id), "name": name, "staff_id": uuid_str(staff_id)}


def _item(
    at: datetime,
    step: str,
    scope: str,
    actor: dict,
    summary: str,
    details: dict,
    source: str,
    sample_id: UUID | None = None,
) -> dict:
    return {
        "at": at,
        "step": step,
        "scope": scope,
        "actor": actor,
        "summary": summary,
        "details": details,
        "source": source,
        "_sample_id": sample_id,
    }


def _real(error: OrderTestEvent) -> dict:
    if error.order_test_id:
        scope = "test"
    elif error.order_sample_id:
        scope = "sample"
    else:
        scope = "order"
    return _item(
        error.occurred_at,
        error.step,
        scope,
        _actor(error.actor_user_id, error.actor_name, error.staff_id),
        error.summary,
        error.details,
        "event",
        error.order_sample_id,
    )


def _covered(
    derived: dict, reals: list[dict], tolerance: timedelta = TOLERANCE
) -> bool:
    steps = EQUIVALENT.get(derived["step"], {derived["step"]})
    for real_event in reals:
        if (
            real_event["step"] not in steps
            or abs(real_event["at"] - derived["at"]) > tolerance
        ):
            continue
        if all(
            str(derived["details"][match_key])
            == str(real_event["details"].get(match_key))
            for match_key in MATCH_KEYS
            if match_key in derived["details"]
        ):
            return True
    return False


async def _queue_items(session: AsyncSession, order: Order) -> list[dict]:
    step_names = await catalogs_service.trace_step_names(session)
    history = (
        await session.execute(
            select(QueueStatusHistory)
            .where(QueueStatusHistory.queue_entry_id == order.queue_entry_id)
            .order_by(QueueStatusHistory.changed_at)
        )
    ).scalars()
    out = []
    for history_entry in history:
        step = (
            "queue.returned"
            if history_entry.kind == "return"
            else _STATUS_STEP[history_entry.to_status]
        )
        out.append(
            _item(
                history_entry.changed_at,
                step,
                "order",
                _actor(history_entry.actor_user_id, history_entry.actor),
                step_names.get(step, step),
                {
                    "from_status": history_entry.from_status,
                    "to_status": history_entry.to_status,
                    "kind": history_entry.kind,
                },
                "derived",
            )
        )
    return out


def _sample_items(samples: list[OrderSample]) -> list[dict]:
    out = []
    for sample in samples:
        base = {"sample_id": str(sample.id), "sample_type": sample.sample_type_code}
        stamps = (
            (
                "labels.printed",
                sample.labels_printed_at,
                sample.labels_printed_by,
                sample.labels_printed_by_user_id,
                f"Etiquetas del tubo {sample.name} impresas",
            ),
            (
                "sample.collected",
                sample.collected_at,
                sample.collected_by,
                sample.collected_by_user_id,
                f"Tubo {sample.name} marcado como tomado",
            ),
            (
                "lab.received",
                sample.received_at,
                sample.received_by,
                sample.received_by_user_id,
                f"Tubo {sample.name} recibido en laboratorio",
            ),
        )
        for step, at, by, by_id, text in stamps:
            if at is not None:
                out.append(
                    _item(
                        at,
                        step,
                        "sample",
                        _actor(by_id, by),
                        text,
                        dict(base),
                        "derived",
                        sample.id,
                    )
                )
    return out


async def _precondition_items(session: AsyncSession, order: Order) -> list[dict]:
    rows = (
        await session.execute(
            select(OrderPrecondition).where(OrderPrecondition.order_id == order.id)
        )
    ).scalars()
    preconditions = list(rows)
    out = []
    for stage in ("reception", "sampling"):
        groups: dict[tuple, list[OrderPrecondition]] = {}
        for precondition in preconditions:
            at = getattr(precondition, f"{stage}_checked_at")
            if at is not None:
                key = (
                    at,
                    getattr(precondition, f"{stage}_checked_by"),
                    getattr(precondition, f"{stage}_checked_by_user_id"),
                )
                groups.setdefault(key, []).append(precondition)
        for (at, by, by_id), group in groups.items():
            unmet = sorted(
                precondition.key
                for precondition in group
                if getattr(precondition, f"{stage}_met") is False
            )
            out.append(
                _item(
                    at,
                    "precondition.checked",
                    "order",
                    _actor(by_id, by),
                    f"Verificación de precondiciones ({stage}): "
                    f"{len(group) - len(unmet)} cumplen, {len(unmet)} no",
                    {"stage": stage, "checked": len(group), "unmet_keys": unmet},
                    "derived",
                )
            )
    return out


async def _test_items(session: AsyncSession, test: OrderTest) -> list[dict]:
    out = [
        _item(
            test.created_at,
            "order.test_added",
            "test",
            _actor(test.created_by_user_id, test.created_by),
            f"Prueba {test.test_code} agregada a la orden",
            {"test_code": test.test_code, "area_code": test.area_code},
            "derived",
        )
    ]
    results = (
        await session.execute(
            select(OrderResult)
            .where(
                OrderResult.order_test_id == test.id,
                OrderResult.entered_at.isnot(None),
            )
            .order_by(OrderResult.sort_order)
        )
    ).scalars()
    for result in results:
        out.append(
            _item(
                result.entered_at,
                "result.entered",
                "test",
                _actor(result.entered_by_user_id, result.entered_by),
                f"{result.analyte_name} capturado (último valor)",
                {
                    "analyte_code": result.analyte_code,
                    "after": (result.value or {}).get("v"),
                    "flag": result.flag,
                },
                "derived",
            )
        )
    if test.validated_at is not None:
        out.append(
            _item(
                test.validated_at,
                "test.validated",
                "test",
                _actor(
                    test.validated_by_user_id,
                    test.validated_by_name,
                    as_uuid(test.validated_by_id),
                ),
                f"Prueba {test.test_code} validada",
                {"validated_by": test.validated_by_name},
                "derived",
            )
        )
    return out


async def _activation_items(session: AsyncSession, order: Order) -> list[dict]:
    code = (
        await session.execute(
            select(ActivationCode).where(ActivationCode.order_id == order.id)
        )
    ).scalar_one_or_none()
    if code is None:
        return []
    out = [
        _item(
            code.created_at,
            "activation.issued",
            "order",
            _actor(code.created_by_user_id, None),
            "Código de activación emitido",
            {"expires_at": code.expires_at.isoformat()},
            "derived",
        )
    ]
    if code.used_at is not None:
        out.append(
            _item(
                code.used_at,
                "activation.used",
                "order",
                _actor(None, None),
                "Código de activación usado",
                {"client": code.used_by_client},
                "derived",
            )
        )
    return out


async def build_trace(
    session: AsyncSession, order: Order, test: OrderTest, page: int, page_size: int
) -> dict:
    """Linea de tiempo cronologica (ascendente) y paginada de una prueba."""
    all_samples = (
        await session.execute(
            select(OrderSample).where(OrderSample.order_id == order.id)
        )
    ).scalars()
    samples = [
        all_sample
        for all_sample in all_samples
        if test.test_code in (all_sample.test_codes or [])
    ]
    rows = (
        await session.execute(
            select(OrderTestEvent)
            .where(
                OrderTestEvent.order_id == order.id,
                or_(
                    OrderTestEvent.order_test_id == test.id,
                    and_(
                        OrderTestEvent.order_test_id.is_(None),
                        or_(
                            OrderTestEvent.order_sample_id.is_(None),
                            OrderTestEvent.order_sample_id.in_(
                                [sample.id for sample in samples]
                            ),
                        ),
                    ),
                ),
            )
            .order_by(OrderTestEvent.occurred_at, OrderTestEvent.id)
        )
    ).scalars()
    reals = [_real(row) for row in rows]
    candidates = [
        *await _queue_items(session, order),
        *await _test_items(session, test),
        *_sample_items(samples),
        *await _precondition_items(session, order),
        *await _activation_items(session, order),
    ]
    tolerance = timedelta(
        seconds=await runtime_settings.get("trace.dedup_tolerance_seconds")
    )
    derived = [
        candidate
        for candidate in candidates
        if not _covered(candidate, reals, tolerance)
    ]
    merged = sorted(reals + derived, key=lambda i: i["at"])  # estable
    start = (page - 1) * page_size
    events = [
        {
            **{
                key: value
                for key, value in i.items()
                if key not in ("_sample_id", "at")
            },
            "at": i["at"].isoformat(),
        }
        for i in merged[start : start + page_size]
    ]
    return {
        "order_number": order.order_number,
        "order_id": str(order.id),
        "test": {
            "id": str(test.id),
            "code": test.test_code,
            "name": test.test_name,
            "area_code": test.area_code,
            "validation_status": test.validation_status,
            "created_at": test.created_at.isoformat(),
        },
        "events": events,
        "page": page,
        "page_size": page_size,
        "total": len(merged),
    }
