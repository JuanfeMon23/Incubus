import type { QueueStatus } from '../types'
import { createQueueRefresh } from '../utils/queueList'

/**
 * Para pantallas que consultan sus propios endpoints (recepción de laboratorio,
 * resultados): llama a `load` (con debounce) ante eventos de las etapas dadas y
 * al re-sincronizar. `enabled` permite pausar (p. ej. con un modal abierto).
 */
export function useQueueRefresh(
  statuses: QueueStatus[],
  load: () => unknown,
  opts: { debounceMs?: number; enabled?: () => boolean } = {}
) {
  const { subscribe } = useQueueSocket()
  const refresher = createQueueRefresh(statuses, load, { subscribe, ...opts })
  onMounted(refresher.start)
  onBeforeUnmount(refresher.stop)
}
