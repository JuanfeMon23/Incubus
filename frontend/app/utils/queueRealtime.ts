import { ref } from 'vue'
import { originFromApiBase } from './format'
import { LIVE_EVENTS } from './queueLive'
import type { LiveEntry, LiveEvent, LiveEventName } from './queueLive'

/** Parte del `Socket` de socket.io-client que usamos (permite un doble en pruebas). */
export interface SocketLike {
  connected: boolean
  on(event: string, fn: (...args: any[]) => void): unknown
  emit(event: string, ...args: any[]): unknown
  connect(): unknown
  disconnect(): unknown
}

export interface RealtimeSubscriber {
  rooms: string[]
  onEvent(name: LiveEventName, ev: LiveEvent): void
  /** Snapshot (`sync`) de TODOS los `stage:*` unidos por el socket; filtra el suscriptor. */
  onSync(entries: LiveEntry[]): void
}

const SUBSCRIBE_ERRORS: Record<string, string> = {
  forbidden: 'No tienes permiso para recibir actualizaciones en vivo de esta pantalla.',
  too_many_rooms: 'Hay demasiadas pantallas suscritas al tiempo real.',
  invalid_rooms: 'No se pudo activar el tiempo real en esta pantalla.'
}
export const SYNC_FAILED_MESSAGE = 'No se pudo sincronizar el tiempo real. Se reintentará al reconectar.'

/**
 * Solo websocket: con un único proceso no hace falta sticky sessions, evita el
 * long-polling inicial y la doble conexión del upgrade (a cambio, sin fallback
 * si un proxy bloquea WebSocket). Backoff propio de socket.io, configurable.
 */
export function buildSocketOptions(overrides: Record<string, unknown> = {}) {
  return {
    path: '/socket.io',
    transports: ['websocket'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 15000,
    randomizationFactor: 0.5,
    ...overrides
  }
}

/** Abre el socket al namespace `/queue` del backend (origen derivado de la API base). */
export function openQueueSocket(
  ioFn: (url: string, opts: Record<string, unknown>) => SocketLike,
  apiBase: string,
  auth: () => Record<string, unknown> = () => ({}),
  overrides: Record<string, unknown> = {}
): SocketLike {
  return ioFn(`${originFromApiBase(apiBase)}/queue`, {
    ...buildSocketOptions(overrides),
    autoConnect: false,
    auth: (cb: (data: Record<string, unknown>) => void) => cb(auth())
  })
}

/**
 * Conexión compartida de la cola: un socket, rooms contados por suscriptor.
 * El servidor solo AVISA; la escritura sigue siendo REST. En cada (re)conexión
 * se re-suscribe y pide `sync`. `socket = null` (SSR) = inerte.
 */
export function createQueueRealtime(socket: SocketLike | null, opts: { ackTimeoutMs?: number } = {}) {
  const ackTimeoutMs = opts.ackTimeoutMs ?? 5000
  const connected = ref(!!socket?.connected)
  const reconnecting = ref(false)
  const error = ref('')
  const subs = new Set<RealtimeSubscriber>()

  const roomsInUse = () => new Set([...subs].flatMap((s) => s.rooms))

  function ask(event: string, payload?: unknown): Promise<any> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('timeout')), ackTimeoutMs)
      const cb = (res: unknown) => {
        clearTimeout(timer)
        resolve(res)
      }
      if (payload === undefined) socket!.emit(event, cb)
      else socket!.emit(event, payload, cb)
    })
  }

  /** subscribe (atómico) y luego sync; entrega el snapshot a `targets`. */
  async function joinAndSync(targets: RealtimeSubscriber[], rooms: string[]) {
    try {
      if (rooms.length) {
        const joined = await ask('subscribe', { rooms })
        if (!joined?.ok) {
          error.value = SUBSCRIBE_ERRORS[joined?.error] ?? SYNC_FAILED_MESSAGE
          return
        }
      }
      const snap = await ask('sync')
      if (!snap?.ok) {
        error.value = SYNC_FAILED_MESSAGE
        return
      }
      error.value = ''
      for (const s of targets) if (subs.has(s)) s.onSync(snap.entries ?? [])
    } catch {
      error.value = SYNC_FAILED_MESSAGE
    }
  }

  if (socket) {
    socket.on('connect', () => {
      connected.value = true
      reconnecting.value = false
      if (subs.size) void joinAndSync([...subs], [...roomsInUse()])
    })
    socket.on('disconnect', (reason?: string) => {
      connected.value = false
      reconnecting.value = reason !== 'io client disconnect'
    })
    socket.on('connect_error', () => {
      connected.value = false
      reconnecting.value = true
    })
    for (const name of LIVE_EVENTS) {
      socket.on(name, (payload: LiveEvent) => {
        for (const s of [...subs]) {
          try {
            s.onEvent(name, payload)
          } catch (e) {
            console.error('Error al procesar un evento en vivo', e)
          }
        }
      })
    }
    socket.connect()
  }

  /** Suscribe una pantalla; devuelve la función que la des-suscribe. */
  function subscribe(sub: RealtimeSubscriber): () => void {
    subs.add(sub)
    if (socket?.connected) void joinAndSync([sub], sub.rooms)
    return () => {
      if (!subs.delete(sub)) return
      const inUse = roomsInUse()
      const leaving = sub.rooms.filter((r) => !inUse.has(r))
      if (socket?.connected && leaving.length) socket.emit('unsubscribe', { rooms: leaving }, () => {})
    }
  }

  function close() {
    subs.clear()
    socket?.disconnect()
  }

  return { connected, reconnecting, error, subscribe, close }
}
export type QueueRealtime = ReturnType<typeof createQueueRealtime>
