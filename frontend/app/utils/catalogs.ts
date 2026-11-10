import type { CatalogItem, ResultFlagCatalogItem } from '../types'

/** Opciones `{ value, label }` de un `UiSelect` a partir de un catálogo (el label es el nombre; con `withCode`, «code · nombre»). */
export function catalogOptions(items: readonly CatalogItem[], opts: { withCode?: boolean } = {}) {
  return items.map((item) => ({ value: item.code, label: opts.withCode ? `${item.code} · ${item.name}` : item.name }))
}

/** Mapa code → nombre, para etiquetar valores que llegan como code. */
export function namesByCode(items: readonly CatalogItem[]): Record<string, string> {
  return Object.fromEntries(items.map((item) => [item.code, item.name]))
}

/** Nombre de un code; sin coincidencia (o sin code) devuelve `fallback`. */
export function catalogNameOf(items: readonly CatalogItem[], code: string | null | undefined, fallback = ''): string {
  if (!code) return fallback
  return items.find((item) => item.code === code)?.name ?? fallback
}

/** Etiqueta y variante de una bandera de resultado según `result-flags`; `null` si no hay bandera o no existe en el catálogo. */
export function flagPresentation(
  items: readonly ResultFlagCatalogItem[],
  flag: string | null | undefined
): { variant: ResultFlagCatalogItem['variant']; label: string } | null {
  if (!flag) return null
  const found = items.find((item) => item.code === flag)
  return found ? { variant: found.variant, label: found.name } : null
}
