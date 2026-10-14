export interface CheckState {
  met: boolean | null
  note: string
}

export type CheckMap = Record<string, CheckState>

/** Llaves sin respuesta (cumple / no cumple). */
export function unansweredKeys(keys: string[], checks: CheckMap): string[] {
  return keys.filter((k) => checks[k]?.met === null || checks[k]?.met === undefined)
}

/** Llaves marcadas "no cumple" sin nota. */
export function missingNoteKeys(keys: string[], checks: CheckMap): string[] {
  return keys.filter((k) => checks[k]?.met === false && !checks[k]?.note.trim())
}

/** Se puede continuar cuando todas están respondidas y las que no cumplen traen nota. */
export function checksComplete(keys: string[], checks: CheckMap): boolean {
  return unansweredKeys(keys, checks).length === 0 && missingNoteKeys(keys, checks).length === 0
}

/** Cuerpo para la API: una respuesta por llave. */
export function toCheckPayload(keys: string[], checks: CheckMap) {
  return keys.map((key) => ({
    key,
    met: checks[key]?.met ?? null,
    note: checks[key]?.note.trim() || null
  }))
}

/** Estado inicial: reutiliza lo ya guardado (p. ej. la verificación de recepción como sugerencia vacía). */
export function emptyChecks(keys: string[]): CheckMap {
  return Object.fromEntries(keys.map((k) => [k, { met: null, note: '' }]))
}
