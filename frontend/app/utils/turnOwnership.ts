import type { QueueEntry } from '../types'

type Turn = Pick<QueueEntry, 'claimed_by'> & { claimed_by_user_id?: string | null }

/**
 * ¿Puede el usuario devolver/finalizar el turno o marcar sus tubos? Solo quien
 * lo tomó o un supervisor (`incubus.sampling.supervise`). Turno legado
 * (`claimed_by_user_id` nulo): dueño desconocido, no se restringe más que el
 * permiso normal. Sin sesión, un turno con dueño no es accionable. El backend
 * valida igual (403 `not_turn_owner`).
 */
export function canActOnTurn(entry: Turn, user: { id: string } | null | undefined, canSupervise: boolean): boolean {
  if (canSupervise) return true
  const owner = entry.claimed_by_user_id
  if (!owner) return true
  return !!user && user.id === owner
}

/** Aviso legible (mismo texto del backend) para una acción bloqueada; `action` en infinitivo: "devolverlo". */
export function turnOwnerHint(entry: Pick<QueueEntry, 'claimed_by'>, action: string): string {
  return `Este turno lo tomó ${entry.claimed_by || 'otra persona'}. Solo esa persona (o un supervisor) puede ${action}.`
}

/** ¿Es el 403 `not_turn_owner` del backend? */
export function isNotTurnOwnerError(err: unknown): boolean {
  const e = err as { status?: number; code?: string } | null
  return e?.status === 403 && e?.code === 'not_turn_owner'
}
