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
_STATUS_TEXT = {
    "queue.entered": "Ingreso a la cola",
    "queue.reception_claimed": "Recepción tomó al paciente",
    "queue.reception_closed": "Recepción cerrada; orden creada",
    "queue.labels_printed": "Etiquetas impresas; en espera de toma",
    "queue.sampling_claimed": "Toma de muestras tomó al paciente",
    "queue.sampling_finished": "Toma de muestras finalizada",
    "queue.in_laboratory": "Orden en laboratorio",
    "order.finalized": "Orden finalizada",
    "queue.removed": "Paciente retirado de la cola",
    "queue.returned": "Orden devuelta a la etapa anterior",
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


def _real(e: OrderTestEvent) -> dict:
    if e.order_test_id:
        scope = "test"
    elif e.order_sample_id:
        scope = "sample"
    else:
        scope = "order"
    return _item(
        e.occurred_at,
        e.step,
        scope,
        _actor(e.actor_user_id, e.actor_name, e.staff_id),
        e.summary,
        e.details,
        "event",
        e.order_sample_id,
    )


def _covered(
    derived: dict, reals: list[dict], tolerance: timedelta = TOLERANCE
) -> bool:
    steps = EQUIVALENT.get(derived["step"], {derived["step"]})
    for r in reals:
        if r["step"] not in steps or abs(r["at"] - derived["at"]) > tolerance:
            continue
        if all(
            str(derived["details"][k]) == str(r["details"].get(k))
            for k in MATCH_KEYS
            if k in derived["details"]
        ):
            return True
    return False


async def _queue_items(session: AsyncSession, order: Order) -> list[dict]:
    history = (
        await session.execute(
            select(QueueStatusHistory)
            .where(QueueStatusHistory.queue_entry_id == order.queue_entry_id)
            .order_by(QueueStatusHistory.changed_at)
        )
    ).scalars()
    out = []
    for h in history:
        step = "queue.returned" if h.kind == "return" else _STATUS_STEP[h.to_status]
        out.append(
            _item(
                h.changed_at,
                step,
                "order",
                _actor(h.actor_user_id, h.actor),
                _STATUS_TEXT[step],
                {
                    "from_status": h.from_status,
                    "to_status": h.to_status,
                    "kind": h.kind,
                },
                "derived",
            )
        )
    return out


def _sample_items(samples: list[OrderSample]) -> list[dict]:
    out = []
    for s in samples:
        base = {"sample_id": str(s.id), "sample_type": s.sample_type_code}
        stamps = (
            (
                "labels.printed",
                s.labels_printed_at,
                s.labels_printed_by,
                s.labels_printed_by_user_id,
                f"Etiquetas del tubo {s.name} impresas",
            ),
            (
                "sample.collected",
                s.collected_at,
                s.collected_by,
                s.collected_by_user_id,
                f"Tubo {s.name} marcado como tomado",
            ),
            (
                "lab.received",
                s.received_at,
                s.received_by,
                s.received_by_user_id,
                f"Tubo {s.name} recibido en laboratorio",
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
                        s.id,
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
        for p in preconditions:
            at = getattr(p, f"{stage}_checked_at")
            if at is not None:
                key = (
                    at,
                    getattr(p, f"{stage}_checked_by"),
                    getattr(p, f"{stage}_checked_by_user_id"),
                )
                groups.setdefault(key, []).append(p)
        for (at, by, by_id), group in groups.items():
            unmet = sorted(p.key for p in group if getattr(p, f"{stage}_met") is False)
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
    for r in results:
        out.append(
            _item(
                r.entered_at,
                "result.entered",
                "test",
                _actor(r.entered_by_user_id, r.entered_by),
                f"{r.analyte_name} capturado (último valor)",
                {
                    "analyte_code": r.analyte_code,
                    "after": (r.value or {}).get("v"),
                    "flag": r.flag,
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
    samples = [s for s in all_samples if test.test_code in (s.test_codes or [])]
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
                            OrderTestEvent.order_sample_id.in_([s.id for s in samples]),
                        ),
                    ),
                ),
            )
            .order_by(OrderTestEvent.occurred_at, OrderTestEvent.id)
        )
    ).scalars()
    reals = [_real(e) for e in rows]
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
    derived = [d for d in candidates if not _covered(d, reals, tolerance)]
    merged = sorted(reals + derived, key=lambda i: i["at"])  # estable
    start = (page - 1) * page_size
    events = [
        {
            **{k: v for k, v in i.items() if k not in ("_sample_id", "at")},
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
