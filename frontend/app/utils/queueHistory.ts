import type { QueueHistoryRow, QueueStatus } from '../types'

const STAGE_NAMES: Record<QueueStatus, string> = {
  pre_recepcion: 'Pre-recepción',
  en_atencion_recepcion: 'En atención de recepción',
  en_espera_impresion: 'Espera de impresión de etiquetas',
  en_espera_toma_muestras: 'Espera de toma de muestras',
  en_atencion_toma_muestras: 'En atención de toma de muestras',
  toma_finalizada: 'Toma de muestras finalizada',
  en_laboratorio: 'En laboratorio',
  finalizada: 'Finalizada',
  retirado: 'Retirado'
}

const ACTION_LABELS: Record<string, string> = {
  enter: 'Ingreso a la cola',
  advance: 'Avance',
  return: 'Devolución',
  remove: 'Retiro'
}

/** Nombre legible de una etapa de la cola ('' si no hay). */
export function stageName(status: string | null | undefined): string {
  return (status && STAGE_NAMES[status as QueueStatus]) || ''
}

export function actionLabel(kind: string): string {
  return ACTION_LABELS[kind] ?? 'Cambio de estado'
}

/** Quién hizo la acción: "Tú" si es el usuario actual (por id), si no el nombre registrado. */
export function actorLabel(
  row: Pick<QueueHistoryRow, 'actor' | 'actor_user_id'>,
  currentUserId: string | null | undefined
): string {
  if (currentUserId && row.actor_user_id === currentUserId) return 'Tú'
  return row.actor || 'Sin registro'
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' })
}

export interface HistoryItem {
  key: string
  when: string
  action: string
  transition: string
  /** Nombre del motivo de retiro/devolución (nunca el id). */
  reason: string | null
  note: string | null
  who: string
}

/** Líneas de la línea de tiempo, en el orden recibido. */
export function historyItems(rows: QueueHistoryRow[], currentUserId: string | null | undefined): HistoryItem[] {
  return rows.map((r, i) => ({
    key: `${r.changed_at}-${i}`,
    when: formatDateTime(r.changed_at),
    action: actionLabel(r.kind),
    transition: [stageName(r.from_status), stageName(r.to_status)].filter(Boolean).join(' → '),
    reason: r.removal_reason_name?.trim() || r.return_reason_name?.trim() || null,
    note: r.note?.trim() || null,
    who: actorLabel(r, currentUserId)
  }))
}
