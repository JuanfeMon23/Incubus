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
        resolve_transition(S.EN_ATENCION_RECEPCION, S.EN_ESPERA_IMPRESION)
        is TransitionKind.ADVANCE
    )
    assert (
        resolve_transition(S.EN_ESPERA_IMPRESION, S.EN_ESPERA_TOMA_MUESTRAS)
        is TransitionKind.ADVANCE
    )
    assert (
        resolve_transition(S.EN_ESPERA_TOMA_MUESTRAS, S.EN_ATENCION_TOMA_MUESTRAS)
        is TransitionKind.ADVANCE
    )


def test_finalizar_toma_es_un_avance():
    assert (
        resolve_transition(S.EN_ATENCION_TOMA_MUESTRAS, S.TOMA_FINALIZADA)
        is TransitionKind.ADVANCE
    )


def test_flujo_de_laboratorio():
    assert (
        resolve_transition(S.TOMA_FINALIZADA, S.EN_LABORATORIO)
        is TransitionKind.ADVANCE
    )
    assert resolve_transition(S.EN_LABORATORIO, S.FINALIZADA) is TransitionKind.ADVANCE


def test_toma_finalizada_no_retrocede_ni_se_retira():
    for target in (
        S.EN_ESPERA_TOMA_MUESTRAS,
        S.PRE_RECEPCION,
        S.RETIRADO,
        S.FINALIZADA,
    ):
        with pytest.raises(InvalidTransitionError):
            resolve_transition(S.TOMA_FINALIZADA, target)


def test_finalizada_es_terminal():
    for target in (S.EN_LABORATORIO, S.TOMA_FINALIZADA, S.RETIRADO):
        with pytest.raises(InvalidTransitionError):
            resolve_transition(S.FINALIZADA, target)


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
        (S.EN_ATENCION_RECEPCION, S.EN_ESPERA_TOMA_MUESTRAS),
        (S.EN_ESPERA_IMPRESION, S.EN_ATENCION_TOMA_MUESTRAS),
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
