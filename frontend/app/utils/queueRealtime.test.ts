import { describe, expect, it, vi } from 'vitest'
import { io } from 'socket.io-client'
import { createFakeSocket } from '../testing/fakeSocket'
import {
  buildSocketOptions,
  createQueueRealtime,
  openQueueSocket,
  REFUSED_MESSAGE,
  SESSION_ENDED_MESSAGE,
  SYNC_FAILED_MESSAGE
} from './queueRealtime'
import type { RealtimeSubscriber } from './queueRealtime'

// Nunca se abre una conexión real: `io` devuelve el doble.
vi.mock('socket.io-client', () => ({ io: vi.fn() }))

const okResponders = {
  subscribe: () => ({ ok: true, joined: [] }),
  sync: () => ({ ok: true, entries: [{ id: 'a', status: 'pre_recepcion', version: 1 }] })
}
const sub = (rooms: string[]): RealtimeSubscriber & { events: unknown[]; syncs: unknown[] } => {
  const events: unknown[] = []
  const syncs: unknown[] = []
  return { rooms, events, syncs, onEvent: (name, payload) => events.push([name, payload]), onSync: (syncPayload) => syncs.push(syncPayload) }
}
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

describe('openQueueSocket', () => {
  it('conecta al namespace /queue del origen del backend, solo websocket, con auth extensible', () => {
    vi.mocked(io).mockReturnValue(createFakeSocket().socket as never)
    openQueueSocket(io as never, 'http://localhost:8001/api/v1', () => ({ token: 't' }))
    const [url, opts] = vi.mocked(io).mock.calls[0] as unknown as [string, Record<string, any>]
    expect(url).toBe('http://localhost:8001/queue')
    expect(opts).toMatchObject({ path: '/socket.io', transports: ['websocket'], reconnectionDelayMax: 15000 })
    const cb = vi.fn()
    opts.auth(cb)
    expect(cb).toHaveBeenCalledWith({ token: 't' })
  })
  it('auth puede ser asíncrona: entrega la prueba nueva de cada (re)conexión', async () => {
    vi.mocked(io).mockReturnValue(createFakeSocket().socket as never)
    let connectionCount = 0
    openQueueSocket(io as never, 'http://localhost:8001/api/v1', async () => ({ dpop: `jws-${++connectionCount}` }))
    const [, opts] = vi.mocked(io).mock.calls.at(-1) as unknown as [string, Record<string, any>]
    const first = vi.fn()
    const second = vi.fn()
    opts.auth(first)
    opts.auth(second)
    await flush()
    expect(first).toHaveBeenCalledWith({ dpop: 'jws-1' })
    expect(second).toHaveBeenCalledWith({ dpop: 'jws-2' })
  })
  it('el backoff es configurable', () => {
    expect(buildSocketOptions({ reconnectionDelayMax: 5000 }).reconnectionDelayMax).toBe(5000)
  })
})

describe('createQueueRealtime', () => {
  it('al montar una pantalla conectada se suscribe a sus rooms y pide sync', async () => {
    const fakeSocket = createFakeSocket(okResponders)
    fakeSocket.fire('connect')
    const rt = createQueueRealtime(fakeSocket.socket)
    const subscription = sub(['stage:pre_recepcion'])
    rt.subscribe(subscription)
    await flush()
    expect(fakeSocket.emitted.map((emission) => emission.event)).toEqual(['subscribe', 'sync'])
    expect(fakeSocket.emittedEvents('subscribe')).toEqual([{ rooms: ['stage:pre_recepcion'] }])
    expect(subscription.syncs).toHaveLength(1)
  })

  it('al desmontar se des-suscribe solo de los rooms que nadie más usa', async () => {
    const fakeSocket = createFakeSocket(okResponders)
    fakeSocket.fire('connect')
    const rt = createQueueRealtime(fakeSocket.socket)
    const firstUnsubscribe = rt.subscribe(sub(['stage:a', 'stage:b']))
    const off = rt.subscribe(sub(['stage:b', 'stage:c']))
    await flush()
    off()
    expect(fakeSocket.emittedEvents('unsubscribe')).toEqual([{ rooms: ['stage:c'] }])
    firstUnsubscribe()
    expect(fakeSocket.emittedEvents('unsubscribe')[1]).toEqual({ rooms: ['stage:a', 'stage:b'] })
  })

  it('en cada (re)conexión emite subscribe y luego sync con todos los rooms', async () => {
    const fakeSocket = createFakeSocket(okResponders)
    const rt = createQueueRealtime(fakeSocket.socket)
    const subscription = sub(['stage:x'])
    rt.subscribe(subscription)
    fakeSocket.fire('connect')
    await flush()
    fakeSocket.fire('disconnect', 'transport close')
    fakeSocket.fire('connect')
    await flush()
    expect(fakeSocket.emitted.map((emission) => emission.event)).toEqual(['subscribe', 'sync', 'subscribe', 'sync'])
    expect(subscription.syncs).toHaveLength(2)
  })

  it('expone el estado de conexión', () => {
    const fakeSocket = createFakeSocket()
    const rt = createQueueRealtime(fakeSocket.socket)
    expect(rt.connected.value).toBe(false)
    fakeSocket.fire('connect')
    expect([rt.connected.value, rt.reconnecting.value]).toEqual([true, false])
    fakeSocket.fire('disconnect', 'transport close')
    expect([rt.connected.value, rt.reconnecting.value]).toEqual([false, true])
    fakeSocket.fire('connect')
    expect([rt.connected.value, rt.reconnecting.value]).toEqual([true, false])
    fakeSocket.fire('connect_error', new Error('x'))
    expect([rt.connected.value, rt.reconnecting.value]).toEqual([false, true])
  })

  it('reenvía los eventos del servidor a los suscriptores', () => {
    const fakeSocket = createFakeSocket()
    const rt = createQueueRealtime(fakeSocket.socket)
    const subscription = sub(['stage:x'])
    rt.subscribe(subscription)
    fakeSocket.fire('sample:updated', { id: 'a', version: 2 })
    expect(subscription.events).toEqual([['sample:updated', { id: 'a', version: 2 }]])
  })

  it('un error de suscripción deja un mensaje legible y no sincroniza', async () => {
    const fakeSocket = createFakeSocket({ subscribe: () => ({ ok: false, error: 'forbidden' }) })
    fakeSocket.fire('connect')
    const rt = createQueueRealtime(fakeSocket.socket)
    const subscription = sub(['stage:x'])
    rt.subscribe(subscription)
    await flush()
    expect(rt.error.value).toMatch(/permiso/)
    expect(subscription.syncs).toHaveLength(0)
  })

  it('sin ack del servidor reporta el fallo de sincronización', async () => {
    const fakeSocket = createFakeSocket()
    fakeSocket.socket.emit = () => {} // nunca responde
    fakeSocket.fire('connect')
    const rt = createQueueRealtime(fakeSocket.socket, { ackTimeoutMs: 5 })
    rt.subscribe(sub(['stage:x']))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(rt.error.value).toBe(SYNC_FAILED_MESSAGE)
  })

  it('forbidden en la suscripción dice que no tiene permiso para esa etapa', async () => {
    const fakeSocket = createFakeSocket({ subscribe: () => ({ ok: false, error: 'forbidden' }) })
    fakeSocket.fire('connect')
    const rt = createQueueRealtime(fakeSocket.socket)
    rt.subscribe(sub(['stage:x']))
    await flush()
    expect(rt.error.value).toBe('No tienes permiso para ver esta etapa.')
  })

  it('autoConnect:false no conecta hasta open() (solo con sesión)', () => {
    const fakeSocket = createFakeSocket()
    const rt = createQueueRealtime(fakeSocket.socket, { autoConnect: false })
    expect(fakeSocket.calls.connect).toBe(0)
    rt.open()
    expect(fakeSocket.calls.connect).toBe(1)
  })
})

describe('sesión del socket (Leo)', () => {
  it('session_expired: renueva la sesión y reconecta (con prueba nueva)', async () => {
    const fakeSocket = createFakeSocket({ subscribe: () => ({ ok: false, error: 'session_expired' }) })
    fakeSocket.fire('connect')
    const refreshSession = vi.fn().mockResolvedValue(true)
    const rt = createQueueRealtime(fakeSocket.socket, { autoConnect: false, refreshSession })
    rt.subscribe(sub(['stage:x']))
    await flush()
    expect(refreshSession).toHaveBeenCalledTimes(1)
    expect(fakeSocket.calls.connect).toBe(1)
    expect(rt.error.value).toMatch(/sesión/)
  })

  it('session_expired con la sesión terminada: no reconecta y avisa', async () => {
    const fakeSocket = createFakeSocket({ sync: () => ({ ok: false, error: 'session_expired' }), subscribe: () => ({ ok: true }) })
    fakeSocket.fire('connect')
    const rt = createQueueRealtime(fakeSocket.socket, { autoConnect: false, refreshSession: async () => false })
    rt.subscribe(sub(['stage:x']))
    await flush()
    expect(fakeSocket.calls.connect).toBe(0)
    expect(rt.error.value).toBe(SESSION_ENDED_MESSAGE)
    expect(rt.reconnecting.value).toBe(false)
  })

  it('el servidor desconecta (io server disconnect): renueva y reconecta', async () => {
    const fakeSocket = createFakeSocket()
    fakeSocket.fire('connect')
    const refreshSession = vi.fn().mockResolvedValue(true)
    createQueueRealtime(fakeSocket.socket, { autoConnect: false, refreshSession })
    fakeSocket.fire('disconnect', 'io server disconnect')
    await flush()
    expect(refreshSession).toHaveBeenCalledTimes(1)
    expect(fakeSocket.calls.connect).toBe(1)
  })

  it('una desconexión de red no renueva la sesión (socket.io reintenta solo)', async () => {
    const fakeSocket = createFakeSocket()
    fakeSocket.fire('connect')
    const refreshSession = vi.fn().mockResolvedValue(true)
    createQueueRealtime(fakeSocket.socket, { autoConnect: false, refreshSession })
    fakeSocket.fire('disconnect', 'transport close')
    await flush()
    expect(refreshSession).not.toHaveBeenCalled()
  })

  it('conexión rechazada (sin reintento automático): renueva y reintenta; tras dos rechazos para y avisa', async () => {
    const fakeSocket = createFakeSocket()
    const refreshSession = vi.fn().mockResolvedValue(true)
    const rt = createQueueRealtime(fakeSocket.socket, { autoConnect: false, refreshSession })
    fakeSocket.refuse()
    await flush()
    fakeSocket.refuse()
    await flush()
    expect(fakeSocket.calls.connect).toBe(2)
    fakeSocket.refuse()
    await flush()
    expect(fakeSocket.calls.connect).toBe(2)
    expect(refreshSession).toHaveBeenCalledTimes(2)
    expect(rt.error.value).toBe(REFUSED_MESSAGE)
    expect(rt.reconnecting.value).toBe(false)
  })

  it('un rechazo sin sesión válida avisa que la sesión terminó', async () => {
    const fakeSocket = createFakeSocket()
    const rt = createQueueRealtime(fakeSocket.socket, { autoConnect: false, refreshSession: async () => false })
    fakeSocket.refuse()
    await flush()
    expect(fakeSocket.calls.connect).toBe(0)
    expect(rt.error.value).toBe(SESSION_ENDED_MESSAGE)
  })

  it('al conectar bien se reinicia el conteo de rechazos y se limpia el aviso', async () => {
    const fakeSocket = createFakeSocket(okResponders)
    const rt = createQueueRealtime(fakeSocket.socket, { autoConnect: false, refreshSession: async () => true })
    rt.subscribe(sub(['stage:x']))
    fakeSocket.refuse()
    await flush()
    fakeSocket.fire('connect')
    await flush()
    expect(rt.error.value).toBe('')
    fakeSocket.refuse()
    await flush()
    fakeSocket.refuse()
    await flush()
    expect(fakeSocket.calls.connect).toBe(3) // 1 antes de conectar + 2 reintentos (el conteo se reinició)
  })
})
