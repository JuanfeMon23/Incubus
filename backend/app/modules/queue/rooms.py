"""Rooms de Socket.IO de la cola: formato permitido y constructores.

- `stage:<estado>`          todas las entradas de un estado (`QueueStatus`).
- `entry:<uuid>`            una entrada concreta.
- `staff:<professional_id>` las entradas asignadas a un profesional (id de
                            Vladimir: 1-64 caracteres `[A-Za-z0-9_-]`).
"""

import re
from uuid import UUID

from app.modules.queue.transitions import QueueStatus

STAGE, ENTRY, STAFF = "stage", "entry", "staff"
_STAFF_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_STATUSES = {s.value for s in QueueStatus}


def stage_room(status: str) -> str:
    return f"{STAGE}:{status}"


def entry_room(entry_id: UUID | str) -> str:
    return f"{ENTRY}:{entry_id}"


def staff_room(professional_id: str) -> str:
    return f"{STAFF}:{professional_id}"


def is_valid_room(room: object) -> bool:
    if not isinstance(room, str):
        return False
    kind, _, value = room.partition(":")
    if kind == STAGE:
        return value in _STATUSES
    if kind == ENTRY:
        try:
            return str(UUID(value)) == value
        except ValueError:
            return False
    if kind == STAFF:
        return _STAFF_ID.fullmatch(value) is not None
    return False


def stage_statuses(joined: list[str]) -> list[QueueStatus]:
    """Estados de los rooms `stage:*` de una lista de rooms."""
    prefix = f"{STAGE}:"
    return [QueueStatus(r[len(prefix) :]) for r in joined if r.startswith(prefix)]
