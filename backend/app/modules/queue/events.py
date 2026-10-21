"""Eventos de tiempo real de la cola: unico punto de publicacion.

Los routers confirman la transaccion (`commit`) y luego llaman a
`publish_entry(session, entry_id, EVENT)`. Esa funcion arma el mensaje con UNA
consulta (dos en `status_changed`/`removed`, que leen la etapa anterior del
historial), devuelve la entrada (el router la usa como respuesta HTTP) y programa
la entrega en segundo plano: un cliente lento o roto nunca retrasa ni rompe la
respuesta. Cambiar el transporte solo toca `_deliver`.

Mensaje interno (`_deliver` lo recibe; NO sale tal cual a ningun cliente):
{"event": <tipo>, "entry": <QueueEntryRead>} (+ "sample_id", + "previous_status").

Socket.IO, namespace `/queue`. Convencion de nombres `dominio:accion`:

| tipo interno     | evento del cliente | cuando                                    |
|------------------|--------------------|-------------------------------------------|
| `entry_created`  | `entry:created`    | ingreso a la cola                         |
| `status_changed` | `status:changed`   | cambio de estado (claim, call-next,       |
|                  |                    | devolver, cierre de recepcion, imprimir,  |
|                  |                    | fin de toma, laboratorio, finalizada)     |
| `removed`        | `entry:removed`    | retiro (`status="retirado"`)              |
| `entry_updated`  | `entry:updated`    | datos sin cambio de estado: borrador,     |
|                  |                    | verificaciones de precondiciones          |
| `sample_updated` | `sample:updated`   | un tubo cambio; trae `sample_id`          |

Payload (`QueueEntryEvent`, SIN datos personales ni clinicos; el detalle se pide
por REST): {id, status, version, priority_id, assigned_professional_id,
order_number, previous_status?, sample_id?}. `previous_status` solo en
`status:changed` y `entry:removed`; `sample_id` solo en `sample:updated`.
`version` es monotono por entrada: el cliente descarta un evento con version
menor o igual a la que ya tiene. La entrega se serializa (un solo emisor a la
vez), asi que dentro de un proceso llegan en el orden en que se publicaron.

Destino (rooms, sin duplicar entregas): `stage:<status>`, `stage:<previous>` si
cambio de etapa (la pantalla anterior retira el turno), `entry:<id>` y
`staff:<assigned_professional_id>` si hay. Si cambia el profesional asignado, el
anterior se entera por el `stage:` (limitacion conocida).
"""

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from leo_sdk import LeoUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.leo import record_audit
from app.core.realtime import emit_to_rooms
from app.modules.queue import rooms, service
from app.modules.queue.schemas import (
    PatientRead,
    PriorityRead,
    QueueEntryEvent,
    QueueEntryLive,
    QueueEntryRead,
)

log = logging.getLogger(__name__)

ENTRY_CREATED = "entry_created"
STATUS_CHANGED = "status_changed"
REMOVED = "removed"
ENTRY_UPDATED = "entry_updated"
SAMPLE_UPDATED = "sample_updated"

CLIENT_EVENT = {
    ENTRY_CREATED: "entry:created",
    STATUS_CHANGED: "status:changed",
    REMOVED: "entry:removed",
    ENTRY_UPDATED: "entry:updated",
    SAMPLE_UPDATED: "sample:updated",
}
_STAGE_CHANGING = (STATUS_CHANGED, REMOVED)

_PENDING: set[asyncio.Task] = set()


@dataclass(frozen=True)
class AuditInfo:
    """Auditoria en Leo de la mutacion que se publica (opcional).

    `before`/`after` solo con ids, estados y codigos (nunca datos personales).
    `publish_entry` agrega el cambio de etapa cuando el evento la cambia.
    """

    user: LeoUser
    tag: str
    before: Mapping[str, Any] = field(default_factory=dict)
    after: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None


def to_read(
    entry, patient, priority, order_number: str | None = None
) -> QueueEntryRead:
    return QueueEntryRead(
        id=entry.id,
        status=entry.status,
        claimed_by=entry.claimed_by,
        assigned_professional_id=entry.assigned_professional_id,
        assigned_professional_name=entry.assigned_professional_name,
        arrived_at=entry.arrived_at,
        draft=entry.draft,
        patient=PatientRead.model_validate(patient),
        priority=PriorityRead.model_validate(priority),
        order_number=order_number,
        version=entry.version,
    )


async def read_entry(session: AsyncSession, entry_id: UUID) -> QueueEntryRead:
    """Estado actual de la entrada (1 consulta, ignora lo cacheado en la sesion)."""
    return to_read(*await service.get_entry_full(session, entry_id))


def to_live(entry: dict[str, Any]) -> QueueEntryLive:
    """Vista minima (sin PII) de una entrada ya serializada (`QueueEntryRead`)."""
    return QueueEntryLive(
        id=entry["id"],
        status=entry["status"],
        version=entry["version"],
        priority_id=entry["priority"]["id"],
        assigned_professional_id=entry["assigned_professional_id"],
        order_number=entry["order_number"],
    )


def target_rooms(payload: QueueEntryEvent) -> list[str]:
    """Rooms destino de un evento, sin repetir."""
    targets = [rooms.stage_room(payload.status)]
    if payload.previous_status and payload.previous_status != payload.status:
        targets.append(rooms.stage_room(payload.previous_status))
    targets.append(rooms.entry_room(payload.id))
    if payload.assigned_professional_id:
        targets.append(rooms.staff_room(payload.assigned_professional_id))
    return targets


async def _safe(event: str, send) -> None:
    try:
        await send
    except Exception:
        log.exception("No se pudo difundir el evento '%s'", event)


async def _deliver(message: dict[str, Any]) -> None:
    """Entrega por Socket.IO; un fallo se registra y no se propaga."""
    kind = message["event"]
    live = to_live(message["entry"])
    payload = QueueEntryEvent(
        **live.model_dump(),
        previous_status=message.get("previous_status"),
        sample_id=message.get("sample_id"),
    )
    body = payload.model_dump(mode="json")
    for optional in ("previous_status", "sample_id"):
        if body[optional] is None:
            del body[optional]
    await _safe(kind, emit_to_rooms(CLIENT_EVENT[kind], body, target_rooms(payload)))


def _schedule(message: dict[str, Any]) -> None:
    task = asyncio.get_running_loop().create_task(_deliver(message))
    _PENDING.add(task)  # referencia fuerte hasta que termine
    task.add_done_callback(_PENDING.discard)


async def publish_entry(
    session: AsyncSession,
    entry_id: UUID,
    event: str,
    *,
    sample_id: UUID | str | None = None,
    audit: AuditInfo | None = None,
) -> QueueEntryRead:
    """Llamar DESPUES del commit. Devuelve la entrada leida (para la respuesta).

    Con `audit`, registra el evento en Leo (nunca falla la operacion)."""
    read = await read_entry(session, entry_id)
    message: dict[str, Any] = {"event": event, "entry": read.model_dump(mode="json")}
    if event in _STAGE_CHANGING:
        previous = await service.previous_status(session, entry_id, read.status)
        if previous is not None:
            message["previous_status"] = previous
    if sample_id is not None:
        message["sample_id"] = str(sample_id)
    _schedule(message)
    if audit is not None:
        await _audit(audit, entry_id, event, read.status, message)
    return read


async def _audit(
    audit: AuditInfo, entry_id: UUID, event: str, status: str, message: dict[str, Any]
) -> None:
    before, after = dict(audit.before), dict(audit.after)
    if event == ENTRY_CREATED or event in _STAGE_CHANGING:
        before["status"] = message.get("previous_status")
        after["status"] = status
    await record_audit(
        audit.tag,
        audit.user,
        entity_type="queue_entry",
        entity_id=entry_id,
        before=before,
        after=after,
        reason=audit.reason,
    )


async def drain() -> None:
    """Espera a que se entreguen los eventos pendientes (pruebas, apagado)."""
    while _PENDING:
        await asyncio.gather(*list(_PENDING), return_exceptions=True)
