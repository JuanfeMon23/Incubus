"""Mapa unico de estados y transiciones validas de la cola de atencion."""

from enum import StrEnum


class QueueStatus(StrEnum):
    PRE_RECEPCION = "pre_recepcion"
    EN_ATENCION_RECEPCION = "en_atencion_recepcion"
    EN_ESPERA_TOMA_MUESTRAS = "en_espera_toma_muestras"
    EN_ATENCION_TOMA_MUESTRAS = "en_atencion_toma_muestras"
    RETIRADO = "retirado"


class TransitionKind(StrEnum):
    ADVANCE = "advance"
    RETURN = "return"
    REMOVE = "remove"


class InvalidTransitionError(Exception):
    def __init__(self, origin: QueueStatus, target: QueueStatus) -> None:
        self.origin, self.target = origin, target
        super().__init__(f"Transicion no permitida: {origin} -> {target}.")


S = QueueStatus
ACTIVE_STATUSES = (
    S.PRE_RECEPCION,
    S.EN_ATENCION_RECEPCION,
    S.EN_ESPERA_TOMA_MUESTRAS,
    S.EN_ATENCION_TOMA_MUESTRAS,
)

_ADVANCES = {
    (S.PRE_RECEPCION, S.EN_ATENCION_RECEPCION),
    (S.EN_ATENCION_RECEPCION, S.EN_ESPERA_TOMA_MUESTRAS),
    (S.EN_ESPERA_TOMA_MUESTRAS, S.EN_ATENCION_TOMA_MUESTRAS),
}
_RETURNS = {
    (S.EN_ATENCION_RECEPCION, S.PRE_RECEPCION),
    (S.EN_ATENCION_TOMA_MUESTRAS, S.EN_ESPERA_TOMA_MUESTRAS),
}


def resolve_transition(origin: QueueStatus, target: QueueStatus) -> TransitionKind:
    if (origin, target) in _ADVANCES:
        return TransitionKind.ADVANCE
    if (origin, target) in _RETURNS:
        return TransitionKind.RETURN
    if target is S.RETIRADO and origin in ACTIVE_STATUSES:
        return TransitionKind.REMOVE
    raise InvalidTransitionError(origin, target)
