import { CATALOG_CACHE_TTL } from '#leo-client/lib/requestCache'
import { leoErrorMessage } from '#leo-client/lib/errors'
import type { CatalogItem, CatalogSlug } from '../types'
import { catalogNameOf, catalogOptions } from '../utils/catalogs'

/**
 * Catálogo de BD (`GET /catalogs/{slug}`, solo activos; `includeInactive` trae todos).
 * La caché es la de `useLeoAppApi` (`cacheTtl`; cualquier mutación la invalida), así que varios
 * componentes que piden el mismo slug comparten una sola petición. Carga al montar el componente.
 */
export function useCatalog<T extends CatalogItem = CatalogItem>(slug: CatalogSlug, opts: { includeInactive?: boolean } = {}) {
  const api = useLeoAppApi()
  const items = ref<T[]>([]) as Ref<T[]>
  const loading = ref(false)
  const error = ref('')

  async function load() {
    loading.value = true
    error.value = ''
    try {
      items.value = await api.get<T[]>(`/catalogs/${slug}`, {
        cacheTtl: CATALOG_CACHE_TTL,
        ...(opts.includeInactive ? { query: { include_inactive: true } } : {})
      })
    } catch (caughtError) {
      error.value = leoErrorMessage(caughtError)
    } finally {
      loading.value = false
    }
  }
  const ready = load()
  return {
    items,
    loading,
    error,
    ready,
    reload: load,
    options: computed(() => catalogOptions(items.value)),
    optionsWithCode: computed(() => catalogOptions(items.value, { withCode: true })),
    nameOf: (code: string | null | undefined, fallback = '') => catalogNameOf(items.value, code, fallback)
  }
}
