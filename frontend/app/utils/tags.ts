import permissions from '../generated/permissions.json'

/**
 * Permisos (tags de Leo) de Incubus: `incubus.<módulo>.<acción>`. Fuente de
 * verdad: `backend/app/core/permissions.py`, exportada al contrato generado
 * `app/generated/permissions.json` (`uv run python -m app.core.permissions_export`).
 * `TAGS` se mantiene a mano por ergonomía; `tags.test.ts` lo compara con el contrato.
 * Un módulo por pantalla/etapa; `resultsDelivery` es solo API para otros servicios.
 */
const buildTag = (module: string, verb: string) => `incubus.${module}.${verb}`

export const TAGS = {
  preReception: {
    view: buildTag('pre-reception', 'view'),
    enqueue: buildTag('pre-reception', 'enqueue'),
    remove: buildTag('pre-reception', 'remove')
  },
  reception: {
    view: buildTag('reception', 'view'),
    callNext: buildTag('reception', 'call-next'),
    editPatient: buildTag('reception', 'edit-patient'),
    closeReception: buildTag('reception', 'close-reception'),
    return: buildTag('reception', 'return'),
    remove: buildTag('reception', 'remove'),
    supervise: buildTag('reception', 'supervise')
  },
  labelPrinting: {
    view: buildTag('label-printing', 'view'),
    print: buildTag('label-printing', 'print')
  },
  sampling: {
    view: buildTag('sampling', 'view'),
    claim: buildTag('sampling', 'claim'),
    collect: buildTag('sampling', 'collect'),
    finish: buildTag('sampling', 'finish'),
    return: buildTag('sampling', 'return'),
    supervise: buildTag('sampling', 'supervise')
  },
  labReception: {
    view: buildTag('lab-reception', 'view'),
    receive: buildTag('lab-reception', 'receive'),
    unreceive: buildTag('lab-reception', 'unreceive')
  },
  results: {
    view: buildTag('results', 'view'),
    enter: buildTag('results', 'enter'),
    validate: buildTag('results', 'validate'),
    trace: buildTag('results', 'trace')
  },
  resultsDelivery: {
    view: buildTag('results-delivery', 'view')
  },
  queueAdmin: {
    view: buildTag('queue-admin', 'view'),
    create: buildTag('queue-admin', 'create'),
    update: buildTag('queue-admin', 'update'),
    toggle: buildTag('queue-admin', 'toggle')
  },
  // `incubus.settings.update` (evento de auditoría de los cambios) no se concede ni tiene pantalla.
  settings: {
    view: buildTag('settings', 'view'),
    edit: buildTag('settings', 'edit'),
    editSecurity: buildTag('settings', 'edit-security')
  }
} as const

/** Acciones del contrato del backend. */
const contractActions = permissions.modules.flatMap((module) => module.actions)

/** Tags asignables (los eventos de auditoría no), en el orden del catálogo del backend. */
export const ALL_TAGS: string[] = contractActions.filter((action) => action.assignable).map((action) => action.tag)

/** Nombre legible de cada tag del contrato (también de los eventos). */
export const TAG_NAMES: Record<string, string> = Object.fromEntries(contractActions.map((action) => [action.tag, action.name]))

/**
 * Tags asignables del contrato que no están en `TAGS` ni abren una pantalla, cada uno con su
 * motivo. Vacío: todo permiso asignable del backend tiene entrada en `TAGS`.
 */
export const TAGS_WITHOUT_SCREEN: Record<string, string> = {}

/** Los `view` de cada etapa con pantalla: quien tenga alguno puede consultar el historial de un turno. */
export const VIEW_TAGS: string[] = [
  TAGS.preReception.view,
  TAGS.reception.view,
  TAGS.labelPrinting.view,
  TAGS.sampling.view,
  TAGS.labReception.view,
  TAGS.results.view
]
