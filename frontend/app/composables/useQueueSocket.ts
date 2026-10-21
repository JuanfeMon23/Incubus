import { io } from 'socket.io-client'
import { createQueueRealtime, openQueueSocket } from '../utils/queueRealtime'
import type { QueueRealtime, SocketLike } from '../utils/queueRealtime'

let realtime: QueueRealtime | null = null

type SocketAuth = () => Record<string, unknown> | Promise<Record<string, unknown>>

// Extensión de autenticación: `setQueueSocketAuth(fn)` antes de la primera
// conexión (lo hace el plugin `queueSocketAuth.client`). `fn` se evalúa en cada
// (re)conexión y con Leo devuelve `{ dpop: <prueba nueva> }`.
let authPayload: SocketAuth = () => ({})
export function setQueueSocketAuth(fn: SocketAuth) {
  authPayload = fn
}

/**
 * Conexión Socket.IO compartida (singleton por app) al namespace `/queue`.
 * Solo avisa de cambios; las acciones siguen siendo REST. Las pantallas no la
 * usan directo: `useQueueList` / `useQueueRefresh` se suscriben por ella.
 * Expone `connected`, `reconnecting` y `error` (texto legible) para el indicador.
 *
 * Solo conecta con sesión de Leo (el servidor rechaza el handshake sin ella):
 * si aún no hay, espera a que exista y se desconecta al cerrarse. Ante
 * `session_expired`, una desconexión del servidor o un rechazo renueva la
 * sesión (`/auth/me`) y reconecta con una prueba DPoP nueva.
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
    const session = useLeoSession()
    const rt = createQueueRealtime(socket, {
      autoConnect: false,
      refreshSession: async () => {
        await session.ensure(true)
        if (!session.isAuthenticated.value) await session.redirectToLogin('expired')
        return session.isAuthenticated.value
      }
    })
    realtime = rt
    if (socket) {
      // Fuera del ciclo de vida del primer componente que lo pidió.
      effectScope(true).run(() => {
        watch(
          () => session.isAuthenticated.value,
          (authenticated, was) => (authenticated ? rt.open() : was ? rt.close() : undefined),
          { immediate: true }
        )
      })
    }
  }
  return realtime
}
