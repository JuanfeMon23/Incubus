import pytest

from app.modules.queue.transitions import (
    InvalidTransitionError,
    QueueStatus,
    TransitionKind,
    resolve_transition,
)

S = QueueStatus


def test_avances_validos():
    assert (
        resolve_transition(S.PRE_RECEPCION, S.EN_ATENCION_RECEPCION)
        is TransitionKind.ADVANCE
    )
    assert (
        resolve_transition(S.EN_ATENCION_RECEPCION, S.EN_ESPERA_TOMA_MUESTRAS)
        is TransitionKind.ADVANCE
    )
    assert (
        resolve_transition(S.EN_ESPERA_TOMA_MUESTRAS, S.EN_ATENCION_TOMA_MUESTRAS)
        is TransitionKind.ADVANCE
    )


def test_devoluciones_validas():
    assert (
        resolve_transition(S.EN_ATENCION_RECEPCION, S.PRE_RECEPCION)
        is TransitionKind.RETURN
    )
    assert (
        resolve_transition(S.EN_ATENCION_TOMA_MUESTRAS, S.EN_ESPERA_TOMA_MUESTRAS)
        is TransitionKind.RETURN
    )


def test_retiro_desde_cualquier_estado_activo():
    for s in (
        S.PRE_RECEPCION,
        S.EN_ATENCION_RECEPCION,
        S.EN_ESPERA_TOMA_MUESTRAS,
        S.EN_ATENCION_TOMA_MUESTRAS,
    ):
        assert resolve_transition(s, S.RETIRADO) is TransitionKind.REMOVE


@pytest.mark.parametrize(
    ("origen", "destino"),
    [
        (S.PRE_RECEPCION, S.EN_ESPERA_TOMA_MUESTRAS),
        (S.PRE_RECEPCION, S.PRE_RECEPCION),
        (S.EN_ESPERA_TOMA_MUESTRAS, S.PRE_RECEPCION),
        (S.EN_ESPERA_TOMA_MUESTRAS, S.EN_ATENCION_RECEPCION),
        (S.EN_ATENCION_TOMA_MUESTRAS, S.PRE_RECEPCION),
        (S.RETIRADO, S.PRE_RECEPCION),
        (S.RETIRADO, S.RETIRADO),
    ],
)
def test_invalidas(origen, destino):
    with pytest.raises(InvalidTransitionError):
        resolve_transition(origen, destino)
