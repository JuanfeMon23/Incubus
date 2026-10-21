"""Catalogo de modulos y acciones de Incubus en Leo + dependencias de permiso.

Un modulo por pantalla/etapa del flujo; tags `incubus.<modulo>.<accion>` con
nombre legible en espanol. Se publica con `python -m app.core.leo_sync`.

Las pantallas cruzan routers (p. ej. «toma de muestras» usa `queue` y `orders`),
por eso el catalogo vive aqui y no en cada modulo de negocio.
"""

from typing import Annotated

from leo_sdk import LeoUser

from app.core.leo import APP_SLUG, auth, catalog, require_any_action


def _module(slug: str, name: str, description: str) -> str:
    catalog.module(slug, name, description)
    return slug


def _action(module: str, verb: str, name: str, description: str) -> str:
    catalog.action(module, verb, name, description)
    return f"{APP_SLUG}.{module}.{verb}"


# --- Pre-recepcion -------------------------------------------------------------
_PRE = _module("pre-reception", "Pre-recepción", "Ingreso de pacientes a la cola.")
PRE_VIEW = _action(
    _PRE, "view", "Consultar la cola de pre-recepción",
    "Ver los pacientes en pre-recepción.",
)  # fmt: skip
PRE_ENQUEUE = _action(
    _PRE, "enqueue", "Ingresar pacientes a la cola",
    "Registrar la llegada de un paciente (incluye leer la cédula y buscar al "
    "paciente por documento).",
)  # fmt: skip
PRE_REMOVE = _action(
    _PRE, "remove", "Retirar pacientes de la cola",
    "Retirar a un paciente en pre-recepción con un motivo.",
)  # fmt: skip

# --- Recepcion -------------------------------------------------------------------
_REC = _module("reception", "Recepción de órdenes", "Atención del paciente y orden.")
REC_VIEW = _action(
    _REC, "view", "Consultar la recepción de órdenes",
    "Ver los pacientes en atención de recepción.",
)  # fmt: skip
REC_CALL_NEXT = _action(
    _REC, "call-next", "Llamar al siguiente paciente",
    "Tomar al siguiente paciente de pre-recepción.",
)  # fmt: skip
REC_EDIT_PATIENT = _action(
    _REC, "edit-patient", "Editar datos del paciente y la orden",
    "Completar los datos del paciente y elegir los exámenes.",
)  # fmt: skip
REC_CLOSE = _action(
    _REC, "close-reception", "Cerrar recepción de órdenes",
    "Crear la orden y enviarla a impresión de etiquetas.",
)  # fmt: skip
REC_RETURN = _action(
    _REC, "return", "Devolver pacientes a pre-recepción",
    "Deshacer la atención de recepción con un motivo.",
)  # fmt: skip
REC_REMOVE = _action(
    _REC, "remove", "Retirar pacientes en recepción",
    "Retirar a un paciente con un motivo (también en las etapas posteriores a "
    "la recepción).",
)  # fmt: skip

# --- Impresion de etiquetas --------------------------------------------------------
_LBL = _module("label-printing", "Impresión de etiquetas", "Etiquetas de los tubos.")
LBL_VIEW = _action(
    _LBL, "view", "Consultar la impresión de etiquetas",
    "Ver las órdenes en espera de impresión y sus tubos.",
)  # fmt: skip
LBL_PRINT = _action(
    _LBL, "print", "Imprimir etiquetas de tubos",
    "Imprimir o descargar las etiquetas y asignar al profesional de toma.",
)  # fmt: skip

# --- Toma de muestras ---------------------------------------------------------------
_SAM = _module("sampling", "Toma de muestras", "Extracción y marcado de tubos.")
SAM_VIEW = _action(
    _SAM, "view", "Consultar la toma de muestras",
    "Ver los pacientes en espera y en atención de toma.",
)  # fmt: skip
SAM_CLAIM = _action(
    _SAM, "claim", "Tomar turnos de toma de muestras",
    "Tomar a un paciente asignado al profesional.",
)  # fmt: skip
SAM_COLLECT = _action(
    _SAM, "collect", "Marcar tubos tomados",
    "Marcar o desmarcar tubos y registrar la verificación de precondiciones "
    "de la toma.",
)  # fmt: skip
SAM_FINISH = _action(
    _SAM, "finish", "Finalizar la toma de muestras",
    "Cerrar la toma cuando todos los tubos están tomados.",
)  # fmt: skip
SAM_RETURN = _action(
    _SAM, "return", "Devolver pacientes a espera de toma",
    "Deshacer la atención de toma con un motivo.",
)  # fmt: skip
SAM_SUPERVISE = _action(
    _SAM, "supervise", "Gestionar turnos de otros técnicos",
    "Devolver, finalizar o marcar tubos de un turno de toma que tomó otra persona.",
)  # fmt: skip

# `supervise` no protege una ruta: se consulta dentro de los handlers de la toma
# (`queue.ownership`) para saltarse la propiedad del turno.
auth.used_tags.add(SAM_SUPERVISE)

# --- Recepcion en laboratorio -------------------------------------------------------
_LAB = _module("lab-reception", "Recepción en laboratorio", "Entrada de tubos.")
LAB_VIEW = _action(
    _LAB, "view", "Consultar la recepción en laboratorio",
    "Ver las órdenes con tubos por recibir.",
)  # fmt: skip
LAB_RECEIVE = _action(
    _LAB, "receive", "Recibir tubos en el laboratorio",
    "Marcar la entrada de un tubo al laboratorio.",
)  # fmt: skip
LAB_UNRECEIVE = _action(
    _LAB, "unreceive", "Deshacer la recepción de tubos",
    "Desmarcar un tubo recibido por error.",
)  # fmt: skip

# --- Resultados -----------------------------------------------------------------------
_RES = _module("results", "Resultados", "Captura y validación de resultados.")
RES_VIEW = _action(
    _RES, "view", "Consultar resultados por validar",
    "Ver las órdenes y exámenes de las áreas del profesional.",
)  # fmt: skip
RES_ENTER = _action(
    _RES, "enter", "Capturar resultados",
    "Guardar los valores de un examen sin validarlo.",
)  # fmt: skip
RES_VALIDATE = _action(
    _RES, "validate", "Validar resultados",
    "Validar un examen; al validar toda la orden se finaliza.",
)  # fmt: skip

# --- Entrega de resultados (API para otro servicio) ------------------------------
_DEL = _module(
    "results-delivery", "Entrega de resultados",
    "API de resultados finalizados para otras aplicaciones.",
)  # fmt: skip
DEL_VIEW = _action(
    _DEL, "view", "Consultar resultados entregados",
    "Leer los resultados finalizados de una orden (JSON y PDF). Acepta "
    "credenciales de servicio.",
)  # fmt: skip

# Etapa (estado de la cola) -> permiso `view` de la pantalla que la muestra.
# Fuente unica para `GET /queue`, `GET /queue/{id}` y los rooms de Socket.IO.
STAGE_VIEW: dict[str, str] = {
    "pre_recepcion": PRE_VIEW,
    "en_atencion_recepcion": REC_VIEW,
    "en_espera_impresion": LBL_VIEW,
    "en_espera_toma_muestras": SAM_VIEW,
    "en_atencion_toma_muestras": SAM_VIEW,
    "toma_finalizada": LAB_VIEW,
    "en_laboratorio": RES_VIEW,
    "finalizada": RES_VIEW,
    "retirado": REC_VIEW,
}
ANY_STAGE_VIEW = tuple(dict.fromkeys(STAGE_VIEW.values()))

# Accion sobre una entrada -> tag segun la etapa en la que esta.
CLAIM_BY_STATUS = {"pre_recepcion": REC_CALL_NEXT, "en_espera_toma_muestras": SAM_CLAIM}
RETURN_BY_STATUS = {
    "en_atencion_recepcion": REC_RETURN,
    "en_atencion_toma_muestras": SAM_RETURN,
}
REMOVE_BY_STATUS = {
    "pre_recepcion": PRE_REMOVE,
    "en_atencion_recepcion": REC_REMOVE,
    "en_espera_impresion": REC_REMOVE,
    "en_espera_toma_muestras": REC_REMOVE,
    "en_atencion_toma_muestras": REC_REMOVE,
}
# Verificacion de precondiciones por etapa.
CHECKS_BY_STAGE = {"reception": REC_EDIT_PATIENT, "sampling": SAM_COLLECT}


def _unique(tags: dict[str, str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tags.values()))


_one = auth.require_action
CanEnqueue = Annotated[LeoUser, _one(PRE_ENQUEUE)]
CanCallNext = Annotated[LeoUser, _one(REC_CALL_NEXT)]
CanEditPatient = Annotated[LeoUser, _one(REC_EDIT_PATIENT)]
CanCloseReception = Annotated[LeoUser, _one(REC_CLOSE)]
CanViewLabels = Annotated[LeoUser, _one(LBL_VIEW)]
CanPrintLabels = Annotated[LeoUser, _one(LBL_PRINT)]
CanCollect = Annotated[LeoUser, _one(SAM_COLLECT)]
CanFinishSampling = Annotated[LeoUser, _one(SAM_FINISH)]
CanViewLab = Annotated[LeoUser, _one(LAB_VIEW)]
CanReceive = Annotated[LeoUser, _one(LAB_RECEIVE)]
CanUnreceive = Annotated[LeoUser, _one(LAB_UNRECEIVE)]
CanViewResults = Annotated[LeoUser, _one(RES_VIEW)]
CanEnterResults = Annotated[LeoUser, _one(RES_ENTER)]
CanValidateResults = Annotated[LeoUser, _one(RES_VALIDATE)]
CanViewDelivery = Annotated[LeoUser, _one(DEL_VIEW)]

# Varios tags posibles (basta uno); el de la etapa concreta se exige despues
# con `authorize` cuando depende del estado de la entrada.
CanViewAnyStage = Annotated[LeoUser, require_any_action(*ANY_STAGE_VIEW)]
CanHandlePatients = Annotated[
    LeoUser, require_any_action(PRE_ENQUEUE, REC_EDIT_PATIENT)
]
CanClaim = Annotated[LeoUser, require_any_action(*_unique(CLAIM_BY_STATUS))]
CanReturn = Annotated[LeoUser, require_any_action(*_unique(RETURN_BY_STATUS))]
CanRemove = Annotated[LeoUser, require_any_action(*_unique(REMOVE_BY_STATUS))]
CanCheck = Annotated[LeoUser, require_any_action(*_unique(CHECKS_BY_STAGE))]
