"""Propiedad del turno de toma de muestras.

Quien tomo el turno (`claim` en espera de toma) es quien lo devuelve, lo
finaliza y marca/desmarca sus tubos; otra persona solo con el permiso
`incubus.sampling.supervise`. La comparacion es por id de usuario de Leo
(`queue_entries.claimed_by_user_id`).

Turno LEGADO: tomado antes de la migracion 0007 (`claimed_by` con nombre pero
`claimed_by_user_id` NULL) = propietario desconocido; no se puede comparar, asi
que se permite a quien tenga el permiso normal de la accion (bloquearlo dejaria
el turno sin salida). Los turnos nuevos siempre llevan el id.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from leo_sdk import LeoUser

from app.core.exceptions import ForbiddenError
from app.core.leo import Actor, audit_denied
from app.core.permissions import SAM_SUPERVISE


class NotTurnOwnerError(ForbiddenError):
    code = "not_turn_owner"


def can_supervise(user: LeoUser) -> bool:
    return user.can(SAM_SUPERVISE)


def ensure_turn_owner(entry, actor: Actor, *, supervisor: bool, action: str) -> None:
    """Exige ser quien tomo el turno (o supervisor). `entry` va bloqueada."""
    owner_id = entry.claimed_by_user_id
    if supervisor or owner_id is None or owner_id == actor.user_id:
        return
    raise NotTurnOwnerError(
        f"Este turno lo tomó {entry.claimed_by or 'otra persona'}. "
        f"Solo esa persona (o un supervisor) puede {action}.",
        {"claimed_by": entry.claimed_by},
    )


@asynccontextmanager
async def audit_not_owner(
    request: Request, user: LeoUser, tag: str
) -> AsyncIterator[None]:
    """Registra el evento `denied` en Leo si el bloque lanza `NotTurnOwnerError`
    (la excepcion se propaga: el handler la responde 403 `not_turn_owner`)."""
    try:
        yield
    except NotTurnOwnerError:
        await audit_denied(request, user, tag)
        raise
