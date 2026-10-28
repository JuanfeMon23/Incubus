import permissions from '../generated/permissions.json'

/**
 * Permisos (tags de Leo) de Incubus: `incubus.<módulo>.<acción>`. Fuente de
 * verdad: `backend/app/core/permissions.py`, exportada al contrato generado
 * `app/generated/permissions.json` (`uv run python -m app.core.permissions_export`).
 * `TAGS` se mantiene a mano por ergonomía; `tags.test.ts` lo compara con el contrato.
 * Un módulo por pantalla/etapa; `resultsDelivery` es solo API para otros servicios.
 */
const t = (module: string, verb: string) => `incubus.${module}.${verb}`

export const TAGS = {
  preReception: {
    view: t('pre-reception', 'view'),
    enqueue: t('pre-reception', 'enqueue'),
    remove: t('pre-reception', 'remove')
  },
  reception: {
    view: t('reception', 'view'),
    callNext: t('reception', 'call-next'),
    editPatient: t('reception', 'edit-patient'),
    closeReception: t('reception', 'close-reception'),
    return: t('reception', 'return'),
    remove: t('reception', 'remove'),
    supervise: t('reception', 'supervise')
  },
  labelPrinting: {
    view: t('label-printing', 'view'),
    print: t('label-printing', 'print')
  },
  sampling: {
    view: t('sampling', 'view'),
    claim: t('sampling', 'claim'),
    collect: t('sampling', 'collect'),
    finish: t('sampling', 'finish'),
    return: t('sampling', 'return'),
    supervise: t('sampling', 'supervise')
  },
  labReception: {
    view: t('lab-reception', 'view'),
    receive: t('lab-reception', 'receive'),
    unreceive: t('lab-reception', 'unreceive')
  },
  results: {
    view: t('results', 'view'),
    enter: t('results', 'enter'),
    validate: t('results', 'validate'),
    trace: t('results', 'trace')
  },
  resultsDelivery: {
    view: t('results-delivery', 'view')
  },
  queueAdmin: {
    view: t('queue-admin', 'view'),
    create: t('queue-admin', 'create'),
    update: t('queue-admin', 'update'),
    toggle: t('queue-admin', 'toggle')
  },
  // `incubus.settings.update` (evento de auditoría de los cambios) no se concede ni tiene pantalla.
  settings: {
    view: t('settings', 'view'),
    edit: t('settings', 'edit'),
    editSecurity: t('settings', 'edit-security')
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
