"""Mapa unico de estados y transiciones validas de la cola de atencion."""

from enum import StrEnum


class QueueStatus(StrEnum):
    PRE_RECEPCION = "pre_recepcion"
    EN_ATENCION_RECEPCION = "en_atencion_recepcion"
    EN_ESPERA_IMPRESION = "en_espera_impresion"
    EN_ESPERA_TOMA_MUESTRAS = "en_espera_toma_muestras"
    EN_ATENCION_TOMA_MUESTRAS = "en_atencion_toma_muestras"
    TOMA_FINALIZADA = "toma_finalizada"
    EN_LABORATORIO = "en_laboratorio"
    FINALIZADA = "finalizada"
    RETIRADO = "retirado"


class TransitionKind(StrEnum):
    ADVANCE = "advance"
    RETURN = "return"
    REMOVE = "remove"


class InvalidTransitionError(Exception):
    def __init__(self, origin: QueueStatus, target: QueueStatus) -> None:
        self.origin, self.target = origin, target
        super().__init__(f"Transicion no permitida: {origin} -> {target}.")


Status = QueueStatus
ACTIVE_STATUSES = (
    Status.PRE_RECEPCION,
    Status.EN_ATENCION_RECEPCION,
    Status.EN_ESPERA_IMPRESION,
    Status.EN_ESPERA_TOMA_MUESTRAS,
    Status.EN_ATENCION_TOMA_MUESTRAS,
)

_ADVANCES = {
    (Status.PRE_RECEPCION, Status.EN_ATENCION_RECEPCION),
    (Status.EN_ATENCION_RECEPCION, Status.EN_ESPERA_IMPRESION),
    (Status.EN_ESPERA_IMPRESION, Status.EN_ESPERA_TOMA_MUESTRAS),
    (Status.EN_ESPERA_TOMA_MUESTRAS, Status.EN_ATENCION_TOMA_MUESTRAS),
    (Status.EN_ATENCION_TOMA_MUESTRAS, Status.TOMA_FINALIZADA),
    (Status.TOMA_FINALIZADA, Status.EN_LABORATORIO),
    (Status.EN_LABORATORIO, Status.FINALIZADA),
}
_RETURNS = {
    (Status.EN_ATENCION_RECEPCION, Status.PRE_RECEPCION),
    (Status.EN_ATENCION_TOMA_MUESTRAS, Status.EN_ESPERA_TOMA_MUESTRAS),
}

# Derivados de los mapas de arriba (unica fuente de verdad):
# `claim` toma al paciente desde pre-recepcion o espera de toma de muestras;
# `return` deshace una atencion volviendo a la fila anterior.
CLAIM_TARGET: dict[QueueStatus, QueueStatus] = {
    origin: target
    for origin, target in _ADVANCES
    if origin in (Status.PRE_RECEPCION, Status.EN_ESPERA_TOMA_MUESTRAS)
}
RETURN_TARGET: dict[QueueStatus, QueueStatus] = dict(_RETURNS)


def resolve_transition(origin: QueueStatus, target: QueueStatus) -> TransitionKind:
    if (origin, target) in _ADVANCES:
        return TransitionKind.ADVANCE
    if (origin, target) in _RETURNS:
        return TransitionKind.RETURN
    if target is Status.RETIRADO and origin in ACTIVE_STATUSES:
        return TransitionKind.REMOVE
    raise InvalidTransitionError(origin, target)
