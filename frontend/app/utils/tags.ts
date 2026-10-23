/**
 * Permisos (tags de Leo) de Incubus: `incubus.<módulo>.<acción>`. Fuente de
 * verdad: `backend/app/core/permissions.py`. Un módulo por pantalla/etapa;
 * `resultsDelivery` es solo API para otros servicios (sin pantalla).
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

/** Todos los tags, en el orden del catálogo del backend. */
export const ALL_TAGS: string[] = Object.values(TAGS).flatMap((module) => Object.values(module))

/** Los `view` de cada etapa con pantalla: quien tenga alguno puede consultar el historial de un turno. */
export const VIEW_TAGS: string[] = [
  TAGS.preReception.view,
  TAGS.reception.view,
  TAGS.labelPrinting.view,
  TAGS.sampling.view,
  TAGS.labReception.view,
  TAGS.results.view
]
