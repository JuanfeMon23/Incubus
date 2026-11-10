import { formatDateTime } from '#andromeda/utils/formatDateTime'
import type { QueueHistoryRow } from '../types'

/** Nombres por code, de los catálogos `queue-statuses` (etapas) y `queue-transition-kinds` (acciones). */
export interface HistoryNames {
  stages?: Record<string, string>
  kinds?: Record<string, string>
}

/** Nombre legible de una etapa de la cola ('' si no hay o no está en el catálogo). */
export function stageName(status: string | null | undefined, stages: Record<string, string> = {}): string {
  return (status && stages[status]) || ''
}

export function actionLabel(kind: string, kinds: Record<string, string> = {}): string {
  return kinds[kind] ?? 'Cambio de estado'
}

/** Quién hizo la acción: "Tú" si es el usuario actual (por id), si no el nombre registrado. */
export function actorLabel(
  row: Pick<QueueHistoryRow, 'actor' | 'actor_user_id'>,
  currentUserId: string | null | undefined
): string {
  if (currentUserId && row.actor_user_id === currentUserId) return 'Tú'
  return row.actor || 'Sin registro'
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
export function historyItems(rows: QueueHistoryRow[], currentUserId: string | null | undefined, names: HistoryNames = {}): HistoryItem[] {
  return rows.map((row, i) => ({
    key: `${row.changed_at}-${i}`,
    when: formatDateTime(row.changed_at),
    action: actionLabel(row.kind, names.kinds),
    transition: [stageName(row.from_status, names.stages), stageName(row.to_status, names.stages)].filter(Boolean).join(' → '),
    reason: row.removal_reason_name?.trim() || row.return_reason_name?.trim() || null,
    note: row.note?.trim() || null,
    who: actorLabel(row, currentUserId)
  }))
}
