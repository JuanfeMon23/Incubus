import type { QueueEntry, QueueStatus } from '../types'
import { createQueueList } from '../utils/queueList'
import type { QueueListDeps } from '../utils/queueList'

/**
 * Lista de la cola filtrada por estados. Se carga por REST al montar y luego se
 * mantiene con los diffs de Socket.IO (no recarga completa por evento).
 * `refresh()` fuerza la recarga completa (tras acciones propias).
 */
export function useQueueList(statuses: QueueStatus[], opts: Pick<QueueListDeps, 'onEvent'> = {}) {
  const api = useApi()
  const { subscribe } = useQueueSocket()
  const list = createQueueList(statuses, {
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
