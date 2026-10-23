import type { QueueAdminItem, QueueAdminKind, QueueAdminPage } from '../types'
import { listParams, PAGE_SIZE } from '../utils/queueAdmin'
import { normalizeSearchTerm } from '#andromeda/utils/search'

/** Llamadas a `/queue-admin/{kind}` (catálogos de la cola) con el cliente de Leo. */
export function useQueueAdminApi(kind: QueueAdminKind) {
  const api = useLeoAppApi()
  const base = `/queue-admin/${kind}`
  return {
    list: (params: ReturnType<typeof listParams>) => api.get<QueueAdminPage>(base, { params }),
    create: (body: Record<string, unknown>) => api.post<QueueAdminItem>(base, body),
    update: (id: string, body: Record<string, unknown>) => api.patch<QueueAdminItem>(`${base}/${id}`, body),
    deactivate: (id: string, reason: string) => api.post<QueueAdminItem>(`${base}/${id}/deactivate`, { reason }),
    activate: (id: string) => api.post<QueueAdminItem>(`${base}/${id}/activate`, {})
  }
}

/**
 * Listado paginado de un catálogo (búsqueda `q`, filtro `is_active`, página). Cambiar
 * búsqueda o filtro vuelve a la página 1; mientras carga conserva las filas anteriores e
 * ignora respuestas viejas. Versión mínima local de `usePaginatedList` de Vladimir
 * (candidato a promover al núcleo: aquí no hay SSR, caché ni sincronía con la URL).
 */
export function useQueueAdminList(kind: QueueAdminKind) {
  const api = useQueueAdminApi(kind)
  const search = ref('')
  const activeFilter = ref<boolean | undefined>(undefined)
  const page = ref(1)
  const rows = ref<QueueAdminItem[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadError = ref<string | null>(null)
  const searchTerm = computed(() => normalizeSearchTerm(search.value))
  let latest = 0

  async function reload() {
    const ticket = ++latest
    loading.value = true
    loadError.value = null
    try {
      const result = await api.list(listParams({ page: page.value, search: search.value, isActive: activeFilter.value }))
      if (ticket !== latest) return
      rows.value = result.items
      total.value = result.total
      // La página quedó fuera de rango (se borró lo último de ella): vuelve a la última con datos.
      const lastPage = Math.max(1, Math.ceil(result.total / PAGE_SIZE))
      if (!result.items.length && page.value > lastPage) page.value = lastPage
    } catch (err) {
      if (ticket !== latest) return
      loadError.value = `No se pudo cargar el listado. ${toUserMessage(err)}`
    } finally {
      if (ticket === latest) loading.value = false
    }
  }

  // Síncrono: el cambio de página ya está hecho cuando corre el watcher de recarga (una sola petición).
  watch([searchTerm, activeFilter], () => { page.value = 1 }, { flush: 'sync' })
  watch([page, searchTerm, activeFilter], reload)
  reload()

  return { rows, total, page, pageSize: PAGE_SIZE, loading, loadError, search, searchTerm, activeFilter, reload }
}
