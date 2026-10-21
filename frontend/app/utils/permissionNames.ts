import { TAGS } from './tags'

/**
 * Nombres legibles de los permisos (tags) de Incubus, para mensajes al
 * usuario ("No tienes permiso para: …"). Son los mismos del catálogo que el
 * backend publica en Leo (`backend/app/core/permissions.py`).
 */
const PERMISSION_NAMES: Record<string, string> = {
  [TAGS.preReception.view]: 'Consultar la cola de pre-recepción',
  [TAGS.preReception.enqueue]: 'Ingresar pacientes a la cola',
  [TAGS.preReception.remove]: 'Retirar pacientes de la cola',
  [TAGS.reception.view]: 'Consultar la recepción de órdenes',
  [TAGS.reception.callNext]: 'Llamar al siguiente paciente',
  [TAGS.reception.editPatient]: 'Editar datos del paciente y la orden',
  [TAGS.reception.closeReception]: 'Cerrar recepción de órdenes',
  [TAGS.reception.return]: 'Devolver pacientes a pre-recepción',
  [TAGS.reception.remove]: 'Retirar pacientes en recepción',
  [TAGS.labelPrinting.view]: 'Consultar la impresión de etiquetas',
  [TAGS.labelPrinting.print]: 'Imprimir etiquetas de tubos',
  [TAGS.sampling.view]: 'Consultar la toma de muestras',
  [TAGS.sampling.claim]: 'Tomar turnos de toma de muestras',
  [TAGS.sampling.collect]: 'Marcar tubos tomados',
  [TAGS.sampling.finish]: 'Finalizar la toma de muestras',
  [TAGS.sampling.return]: 'Devolver pacientes a espera de toma',
  [TAGS.labReception.view]: 'Consultar la recepción en laboratorio',
  [TAGS.labReception.receive]: 'Recibir tubos en el laboratorio',
  [TAGS.labReception.unreceive]: 'Deshacer la recepción de tubos',
  [TAGS.results.view]: 'Consultar resultados por validar',
  [TAGS.results.enter]: 'Capturar resultados',
  [TAGS.results.validate]: 'Validar resultados',
  [TAGS.resultsDelivery.view]: 'Consultar resultados entregados'
}

export function permissionName(tag: string | undefined | null): string | null {
  return (tag && PERMISSION_NAMES[tag]) || null
}

/** Detalle de un 403 `forbidden` del backend: un tag (`action`) o varios alternativos (`any_of`). */
export interface ForbiddenDetails {
  action?: string
  any_of?: string[]
}

/**
 * Mensaje de un 403 `forbidden`: nombra el permiso que falta si se conoce
 * ("No tienes permiso para: X"; con alternativas, "X o Y"); si no, el de respaldo.
 */
export function forbiddenMessage(details: ForbiddenDetails | null | undefined, fallback: string): string {
  const tags = details?.any_of?.length ? details.any_of : details?.action ? [details.action] : []
  const names = [...new Set(tags.map((tag) => permissionName(tag)).filter((n): n is string => !!n))]
  return names.length ? `No tienes permiso para: ${names.join(' o ')}` : fallback
}
