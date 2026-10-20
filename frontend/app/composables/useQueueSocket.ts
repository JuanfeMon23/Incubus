import { io } from 'socket.io-client'
import { createQueueRealtime, openQueueSocket } from '../utils/queueRealtime'
import type { QueueRealtime, SocketLike } from '../utils/queueRealtime'

let realtime: QueueRealtime | null = null

// Punto de extensión para Leo: `setQueueSocketAuth(() => ({ token }))` antes de
// la primera conexión; se evalúa en cada (re)conexión. Hoy el servidor lo ignora.
let authPayload: () => Record<string, unknown> = () => ({})
export function setQueueSocketAuth(fn: () => Record<string, unknown>) {
  authPayload = fn
}

/**
 * Conexión Socket.IO compartida (singleton por app) al namespace `/queue`.
 * Solo avisa de cambios; las acciones siguen siendo REST. Las pantallas no la
 * usan directo: `useQueueList` / `useQueueRefresh` se suscriben por ellas.
 * Expone `connected`, `reconnecting` y `error` (texto legible) para el indicador.
 */
export function useQueueSocket(): QueueRealtime {
  if (!realtime) {
    let socket: SocketLike | null = null
    if (import.meta.client) {
      const base = useRuntimeConfig().public.apiBase
      if (base) {
        socket = openQueueSocket(io as never, base, () => authPayload())
      }
    }
    realtime = createQueueRealtime(socket)
  }
  return realtime
}
