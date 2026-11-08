import pytest

from app.modules.queue.transitions import (
    InvalidTransitionError,
    QueueStatus,
    TransitionKind,
    resolve_transition,
)

Status = QueueStatus


def test_avances_validos():
    assert (
        resolve_transition(Status.PRE_RECEPCION, Status.EN_ATENCION_RECEPCION)
        is TransitionKind.ADVANCE
    )
    assert (
        resolve_transition(Status.EN_ATENCION_RECEPCION, Status.EN_ESPERA_IMPRESION)
        is TransitionKind.ADVANCE
    )
    assert (
        resolve_transition(Status.EN_ESPERA_IMPRESION, Status.EN_ESPERA_TOMA_MUESTRAS)
        is TransitionKind.ADVANCE
    )
    assert (
        resolve_transition(
            Status.EN_ESPERA_TOMA_MUESTRAS, Status.EN_ATENCION_TOMA_MUESTRAS
        )
        is TransitionKind.ADVANCE
    )


def test_finalizar_toma_es_un_avance():
    assert (
        resolve_transition(Status.EN_ATENCION_TOMA_MUESTRAS, Status.TOMA_FINALIZADA)
        is TransitionKind.ADVANCE
    )


def test_flujo_de_laboratorio():
    assert (
        resolve_transition(Status.TOMA_FINALIZADA, Status.EN_LABORATORIO)
        is TransitionKind.ADVANCE
    )
    assert (
        resolve_transition(Status.EN_LABORATORIO, Status.FINALIZADA)
        is TransitionKind.ADVANCE
    )


def test_toma_finalizada_no_retrocede_ni_se_retira():
    for target in (
        Status.EN_ESPERA_TOMA_MUESTRAS,
        Status.PRE_RECEPCION,
        Status.RETIRADO,
        Status.FINALIZADA,
    ):
        with pytest.raises(InvalidTransitionError):
            resolve_transition(Status.TOMA_FINALIZADA, target)


def test_finalizada_es_terminal():
    for target in (Status.EN_LABORATORIO, Status.TOMA_FINALIZADA, Status.RETIRADO):
        with pytest.raises(InvalidTransitionError):
            resolve_transition(Status.FINALIZADA, target)


def test_devoluciones_validas():
    assert (
        resolve_transition(Status.EN_ATENCION_RECEPCION, Status.PRE_RECEPCION)
        is TransitionKind.RETURN
    )
    assert (
        resolve_transition(
            Status.EN_ATENCION_TOMA_MUESTRAS, Status.EN_ESPERA_TOMA_MUESTRAS
        )
        is TransitionKind.RETURN
    )


def test_retiro_desde_cualquier_estado_activo():
    for status in (
        Status.PRE_RECEPCION,
        Status.EN_ATENCION_RECEPCION,
        Status.EN_ESPERA_TOMA_MUESTRAS,
        Status.EN_ATENCION_TOMA_MUESTRAS,
    ):
        assert resolve_transition(status, Status.RETIRADO) is TransitionKind.REMOVE


@pytest.mark.parametrize(
    ("origen", "destino"),
    [
        (Status.PRE_RECEPCION, Status.EN_ESPERA_TOMA_MUESTRAS),
        (Status.EN_ATENCION_RECEPCION, Status.EN_ESPERA_TOMA_MUESTRAS),
        (Status.EN_ESPERA_IMPRESION, Status.EN_ATENCION_TOMA_MUESTRAS),
        (Status.PRE_RECEPCION, Status.PRE_RECEPCION),
        (Status.EN_ESPERA_TOMA_MUESTRAS, Status.PRE_RECEPCION),
        (Status.EN_ESPERA_TOMA_MUESTRAS, Status.EN_ATENCION_RECEPCION),
        (Status.EN_ATENCION_TOMA_MUESTRAS, Status.PRE_RECEPCION),
        (Status.RETIRADO, Status.PRE_RECEPCION),
        (Status.RETIRADO, Status.RETIRADO),
    ],
)
def test_invalidas(origen, destino):
    with pytest.raises(InvalidTransitionError):
        resolve_transition(origen, destino)
