import type { QueueEntry, QueueStatus } from '../types'

/** Vista mínima (sin datos personales) que el servidor envía por Socket.IO. */
export interface LiveEntry {
  id: string
  status: QueueStatus
  version: number
  priority_id: string
  assigned_professional_id: string | null
  order_number: string | null
}
export interface LiveEvent extends LiveEntry {
  previous_status?: QueueStatus
  sample_id?: string
}

export const LIVE_EVENTS = [
  'entry:created',
  'status:changed',
  'entry:removed',
  'entry:updated',
  'sample:updated'
] as const
export type LiveEventName = (typeof LIVE_EVENTS)[number]

export const stageRoom = (status: QueueStatus) => `stage:${status}`

export type EventDecision = 'ignore' | 'remove' | 'patch' | 'fetch'

/**
 * Qué hacer con un evento en una pantalla que lista las etapas `stages`.
 * `seen` es la última versión vista de esa entrada (aunque ya no esté en la
 * lista): un evento con versión menor o igual es viejo o duplicado.
 * - fuera de mis etapas: la retiro si la tenía (cambió de etapa o fue retirada).
 * - entrada nueva o con datos que el evento no trae (prioridad, profesional,
 *   borrador): pido el detalle por REST (`GET /queue/{id}`).
 * - solo cambió estado/orden/versión: aplico el parche sin red.
 */
export function decideEvent(
  name: LiveEventName,
  ev: LiveEvent,
  known: QueueEntry | undefined,
  seen: number | undefined,
  stages: readonly QueueStatus[]
): EventDecision {
  if (seen !== undefined && ev.version <= seen) return 'ignore'
  if (!stages.includes(ev.status)) return known ? 'remove' : 'ignore'
  if (!known) return 'fetch'
  if (
    name === 'entry:updated' ||
    known.priority.id !== ev.priority_id ||
    known.assigned_professional_id !== ev.assigned_professional_id
  ) {
    return 'fetch'
  }
  return 'patch'
}

export function patchEntry(entry: QueueEntry, ev: LiveEvent): QueueEntry {
  return { ...entry, status: ev.status, version: ev.version, order_number: ev.order_number }
}

/** Mismo orden que el servidor: prioridad (rank) y luego llegada. */
export function sortQueue(list: QueueEntry[]): QueueEntry[] {
  return [...list].sort(
    (a, b) => a.priority.rank - b.priority.rank || a.arrived_at.localeCompare(b.arrived_at)
  )
}

/** ¿El snapshot del servidor difiere de la lista local (ids o versiones)? */
export function snapshotDiffers(
  local: readonly Pick<QueueEntry, 'id' | 'version'>[],
  snapshot: readonly Pick<LiveEntry, 'id' | 'version'>[]
): boolean {
  if (local.length !== snapshot.length) return true
  const versions = new Map(local.map((e) => [e.id, e.version]))
  return snapshot.some((s) => versions.get(s.id) !== s.version)
}

/** Mensaje legible cuando marcar/desmarcar un tubo falla (409: el paciente ya no está en toma). */
export const SAMPLING_CONFLICT_MESSAGE =
  'Este paciente ya no está en atención de toma de muestras, por eso no se pueden marcar sus tubos. La lista se actualizó.'

export function sampleToggleError(err: unknown, fallback: (e: unknown) => string): string {
  const e = err as { status?: number; statusCode?: number; response?: { status?: number } } | null
  const status = e?.status ?? e?.statusCode ?? e?.response?.status
  return status === 409 ? SAMPLING_CONFLICT_MESSAGE : fallback(err)
}
