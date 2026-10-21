import { ref } from 'vue'
import { originFromApiBase } from './format'
import { LIVE_EVENTS } from './queueLive'
import type { LiveEntry, LiveEvent, LiveEventName } from './queueLive'

/** Parte del `Socket` de socket.io-client que usamos (permite un doble en pruebas). */
export interface SocketLike {
  connected: boolean
  /** `false` tras un rechazo del servidor: socket.io no reintenta solo. */
  active?: boolean
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
  forbidden: 'No tienes permiso para ver esta etapa.',
  too_many_rooms: 'Hay demasiadas pantallas suscritas al tiempo real.',
  invalid_rooms: 'No se pudo activar el tiempo real en esta pantalla.'
}
export const SYNC_FAILED_MESSAGE = 'No se pudo sincronizar el tiempo real. Se reintentará al reconectar.'
export const SESSION_EXPIRED_MESSAGE = 'Tu sesión venció. Renovando la conexión en vivo…'
export const SESSION_ENDED_MESSAGE = 'Tu sesión terminó. Inicia sesión de nuevo para recibir las actualizaciones en vivo.'
export const REFUSED_MESSAGE = 'No se pudo activar el tiempo real: el servidor rechazó la conexión.'
/** Reintentos tras un rechazo del servidor antes de rendirse (cada uno renueva la sesión). */
export const MAX_REFUSALS = 2

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
  auth: () => Record<string, unknown> | Promise<Record<string, unknown>> = () => ({}),
  overrides: Record<string, unknown> = {}
): SocketLike {
  return ioFn(`${originFromApiBase(apiBase)}/queue`, {
    ...buildSocketOptions(overrides),
    autoConnect: false,
    // Se evalúa en cada (re)conexión: con Leo, una prueba DPoP nueva por intento.
    auth: (cb: (data: Record<string, unknown>) => void) => {
      const data = auth()
      if (data instanceof Promise) void data.then(cb)
      else cb(data)
    }
  })
}

/**
 * Conexión compartida de la cola: un socket, rooms contados por suscriptor.
 * El servidor solo AVISA; la escritura sigue siendo REST. En cada (re)conexión
 * se re-suscribe y pide `sync`. `socket = null` (SSR) = inerte.
 */
export interface QueueRealtimeOptions {
  ackTimeoutMs?: number
  /** `false`: no conecta al crear; la sesión de Leo debe existir antes (llama a `open()`). */
  autoConnect?: boolean
  /**
   * Renueva la sesión (`/auth/me`) y dice si sigue válida. Se usa ante
   * `session_expired`, una desconexión del servidor o un rechazo de la conexión;
   * luego se reconecta con una prueba DPoP nueva.
   */
  refreshSession?: () => Promise<boolean>
}

export function createQueueRealtime(socket: SocketLike | null, opts: QueueRealtimeOptions = {}) {
  const ackTimeoutMs = opts.ackTimeoutMs ?? 5000
  const connected = ref(!!socket?.connected)
  const reconnecting = ref(false)
  const error = ref('')
  const subs = new Set<RealtimeSubscriber>()
  let recovering = false
  let refusals = 0

  /** Sesión vencida o conexión rechazada: renueva la sesión y reconecta con una prueba nueva. */
  async function recoverSession() {
    if (!socket || recovering) return
    if (!opts.refreshSession) return
    recovering = true
    reconnecting.value = true
    try {
      if (await opts.refreshSession()) socket.connect()
      else {
        error.value = SESSION_ENDED_MESSAGE
        reconnecting.value = false
      }
    } catch {
      error.value = SYNC_FAILED_MESSAGE
    } finally {
      recovering = false
    }
  }

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

  /** Error de un ack: mensaje legible; `session_expired` además renueva la sesión y reconecta. */
  function failed(code: string | undefined) {
    if (code === 'session_expired') {
      error.value = SESSION_EXPIRED_MESSAGE
      void recoverSession()
      return
    }
    error.value = SUBSCRIBE_ERRORS[code ?? ''] ?? SYNC_FAILED_MESSAGE
  }

  /** subscribe (atómico) y luego sync; entrega el snapshot a `targets`. */
  async function joinAndSync(targets: RealtimeSubscriber[], rooms: string[]) {
    try {
      if (rooms.length) {
        const joined = await ask('subscribe', { rooms })
        if (!joined?.ok) {
          failed(joined?.error)
          return
        }
      }
      const snap = await ask('sync')
      if (!snap?.ok) {
        failed(snap?.error)
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
      refusals = 0
      if (subs.size) void joinAndSync([...subs], [...roomsInUse()])
    })
    socket.on('disconnect', (reason?: string) => {
      connected.value = false
      reconnecting.value = reason !== 'io client disconnect'
      // El servidor cerró el socket (sesión vencida o revocada): socket.io no reintenta solo.
      if (reason === 'io server disconnect') void recoverSession()
    })
    socket.on('connect_error', () => {
      connected.value = false
      reconnecting.value = true
      // Rechazo del servidor (sin sesión, token vencido…): socket.io no reintenta solo.
      if (socket.active === false) {
        refusals += 1
        if (refusals > MAX_REFUSALS) {
          error.value = REFUSED_MESSAGE
          reconnecting.value = false
        } else void recoverSession()
      }
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
    if (opts.autoConnect !== false) socket.connect()
  }

  /** Abre la conexión (con `autoConnect: false`, cuando ya hay sesión). */
  function open() {
    socket?.connect()
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

  return { connected, reconnecting, error, subscribe, open, close }
}
export type QueueRealtime = ReturnType<typeof createQueueRealtime>
