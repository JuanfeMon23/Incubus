import type { QueueAdminItem, QueueAdminKind, QueueAdminPage } from '../types'
import { listParams, PAGE_SIZE } from '../utils/queueAdmin'

/** Llamadas a `/queue-admin/{kind}` (catálogos de la cola) con el cliente de Leo. */
export function useQueueAdminApi(kind: QueueAdminKind) {
  const api = useLeoAppApi()
  const base = `/queue-admin/${kind}`
  return {
    list: (params: ReturnType<typeof listParams>, signal?: AbortSignal) => api.get<QueueAdminPage>(base, { params, signal }),
    create: (body: Record<string, unknown>) => api.post<QueueAdminItem>(base, body),
    update: (id: string, body: Record<string, unknown>) => api.patch<QueueAdminItem>(`${base}/${id}`, body),
    deactivate: (id: string, reason: string) => api.post<QueueAdminItem>(`${base}/${id}/deactivate`, { reason }),
    activate: (id: string) => api.post<QueueAdminItem>(`${base}/${id}/activate`, {})
  }
}

/**
 * Listado paginado de un catálogo (búsqueda `q`, filtro `is_active`, página) sobre
 * `usePaginatedList` de Andromeda: reset a página 1, respuestas viejas y página fuera de rango
 * los resuelve la capa.
 */
export function useQueueAdminList(kind: QueueAdminKind) {
  const api = useQueueAdminApi(kind)
  const search = ref('')
  const activeFilter = ref<boolean | undefined>(undefined)
  const list = usePaginatedList<QueueAdminItem>({
    fetchPage: (params, { signal }) =>
      api.list(listParams({ page: params.page, search: params.q ?? '', isActive: activeFilter.value }), signal),
    pageSize: PAGE_SIZE,
    filters: [activeFilter],
    search,
    mapError: err => `No se pudo cargar el listado. ${toUserMessage(err)}`
  })
  return { ...list, search, activeFilter }
}
