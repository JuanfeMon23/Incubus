import type { QueueEntry, QueueStatus } from '../types'
import { createQueueList } from '../utils/queueList'
import type { QueueListDeps } from '../utils/queueList'
import { stagesWithView } from '../utils/moduleAccess'

/**
 * Lista de la cola filtrada por estados. Se carga por REST al montar y luego se
 * mantiene con los diffs de Socket.IO (no recarga completa por evento).
 * `refresh()` fuerza la recarga completa (tras acciones propias).
 *
 * Solo pide y se suscribe a las etapas cuyo `view` tiene el usuario (el
 * servidor rechaza el pedido entero si falta alguna); sin ninguna, queda vacía.
 */
export function useQueueList(statuses: QueueStatus[], opts: Pick<QueueListDeps, 'onEvent'> = {}) {
  const api = useApi()
  const { can } = useLeoSession()
  const visible = stagesWithView(statuses, can)
  if (!visible.length) return { entries: ref<QueueEntry[]>([]), error: ref(''), loading: ref(false), refresh: async () => {} }

  const { subscribe } = useQueueSocket()
  const list = createQueueList(visible, {
    subscribe,
    fetchList: (s) => api<QueueEntry[]>(`/queue?${s.map((x) => `status=${x}`).join('&')}`),
    fetchOne: (id) => api<QueueEntry>(`/queue/${id}`),
    toMessage: apiErrorMessage,
    onEvent: opts.onEvent
  })
  onMounted(list.start)
  onBeforeUnmount(list.stop)
  const { entries, error, loading, refresh } = list
  return { entries, error, loading, refresh }
}
