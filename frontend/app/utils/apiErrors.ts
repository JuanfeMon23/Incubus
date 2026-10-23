interface ErrorShape { status?: number, details?: unknown }

/**
 * El tope de `page_size` es un ajuste del backend: un 422 `validation_error` con `details.field = page_size`
 * trae el máximo vigente en `details.max`. `null` si el error es otro.
 */
export function pageSizeMessage(err: unknown): string | null {
  const e = (err ?? {}) as ErrorShape
  const details = (e.details ?? null) as { field?: unknown, max?: unknown } | null
  if (e.status !== 422 || details?.field !== 'page_size') return null
  return typeof details.max === 'number'
    ? `Se pidieron más registros por página de los permitidos (máximo ${details.max}).`
    : 'Se pidieron más registros por página de los permitidos.'
}
