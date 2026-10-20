import type { SocketLike } from './queueRealtime'

type Handler = (...args: any[]) => void
type Responder = (payload: any) => unknown

/** Doble de `Socket` de socket.io-client para pruebas: simula eventos y acks. */
export function createFakeSocket(responders: Record<string, Responder> = {}) {
  const handlers = new Map<string, Handler[]>()
  const emitted: Array<{ event: string; payload?: any }> = []
  const socket = {
    connected: false,
    on(event: string, fn: Handler) {
      handlers.set(event, [...(handlers.get(event) ?? []), fn])
    },
    emit(event: string, ...args: any[]) {
      const ack = typeof args[args.length - 1] === 'function' ? (args.pop() as Handler) : undefined
      emitted.push({ event, payload: args[0] })
      const res = responders[event]?.(args[0])
      if (ack) ack(res)
    },
    connect: () => {},
    disconnect: () => {}
  }
  return {
    socket: socket as SocketLike,
    emitted,
    /** Simula un evento del servidor (`connect`, `disconnect`, `status:changed`…). */
    fire(event: string, ...args: any[]) {
      if (event === 'connect') socket.connected = true
      if (event === 'disconnect' || event === 'connect_error') socket.connected = false
      for (const h of handlers.get(event) ?? []) h(...args)
    },
    emittedEvents: (name: string) => emitted.filter((e) => e.event === name).map((e) => e.payload)
  }
}
