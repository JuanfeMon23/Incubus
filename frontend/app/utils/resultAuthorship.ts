/** Autoría en resultados: quién capturó cada analito y quién validó el examen. Nunca muestra ids. */

const YOU = 'Tú'

/** "Capturado por <nombre>" ("Tú" si es el usuario actual); `null` si no hay dato legible. */
export function enteredByLabel(
  row: { entered_by?: string | null; entered_by_user_id?: string | null },
  currentUserId: string | null | undefined
): string | null {
  if (currentUserId && row.entered_by_user_id === currentUserId) return `Capturado por ${YOU}`
  return row.entered_by ? `Capturado por ${row.entered_by}` : null
}

/**
 * Validación de un examen: `professional` es el profesional de Vladimir que firma
 * (`validated_by`); `executor` es el usuario que ejecutó la validación (distinto).
 * El ejecutor solo se nombra si el backend trae su nombre (`validated_by_user`) o es el usuario actual.
 */
export function validationLabels(
  test: { validated_by?: string | null; validated_by_user_id?: string | null; validated_by_user?: string | null },
  currentUserId: string | null | undefined
): { professional: string | null; executor: string | null } {
  const isMe = !!currentUserId && test.validated_by_user_id === currentUserId
  const who = isMe ? YOU : test.validated_by_user || null
  return {
    professional: test.validated_by ? `Validado por ${test.validated_by} (profesional)` : null,
    executor: who ? `Validación ejecutada por ${who}` : null
  }
}
