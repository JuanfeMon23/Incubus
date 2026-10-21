import type { QueueStatus } from '../types'
import { createQueueRefresh } from '../utils/queueList'
import { stagesWithView } from '../utils/moduleAccess'

/**
 * Para pantallas que consultan sus propios endpoints (recepción de laboratorio,
 * resultados): llama a `load` (con debounce) ante eventos de las etapas dadas y
 * al re-sincronizar. `enabled` permite pausar (p. ej. con un modal abierto).
 * Solo se suscribe a las etapas cuyo `view` tiene el usuario.
 */
export function useQueueRefresh(
  statuses: QueueStatus[],
  load: () => unknown,
  opts: { debounceMs?: number; enabled?: () => boolean } = {}
) {
  const visible = stagesWithView(statuses, useLeoSession().can)
  if (!visible.length) return
  const { subscribe } = useQueueSocket()
  const refresher = createQueueRefresh(visible, load, { subscribe, ...opts })
  onMounted(refresher.start)
  onBeforeUnmount(refresher.stop)
}
