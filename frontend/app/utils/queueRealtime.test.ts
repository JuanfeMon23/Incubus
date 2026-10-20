import { describe, expect, it, vi } from 'vitest'
import { io } from 'socket.io-client'
import { createFakeSocket } from './fakeSocket'
import { buildSocketOptions, createQueueRealtime, openQueueSocket, SYNC_FAILED_MESSAGE } from './queueRealtime'
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
  return { rooms, events, syncs, onEvent: (n, e) => events.push([n, e]), onSync: (s) => syncs.push(s) }
}
const flush = () => new Promise((r) => setTimeout(r, 0))

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
  it('el backoff es configurable', () => {
    expect(buildSocketOptions({ reconnectionDelayMax: 5000 }).reconnectionDelayMax).toBe(5000)
  })
})

describe('createQueueRealtime', () => {
  it('al montar una pantalla conectada se suscribe a sus rooms y pide sync', async () => {
    const f = createFakeSocket(okResponders)
    f.fire('connect')
    const rt = createQueueRealtime(f.socket)
    const s = sub(['stage:pre_recepcion'])
    rt.subscribe(s)
    await flush()
    expect(f.emitted.map((e) => e.event)).toEqual(['subscribe', 'sync'])
    expect(f.emittedEvents('subscribe')).toEqual([{ rooms: ['stage:pre_recepcion'] }])
    expect(s.syncs).toHaveLength(1)
  })

  it('al desmontar se des-suscribe solo de los rooms que nadie más usa', async () => {
    const f = createFakeSocket(okResponders)
    f.fire('connect')
    const rt = createQueueRealtime(f.socket)
    const a = rt.subscribe(sub(['stage:a', 'stage:b']))
    const off = rt.subscribe(sub(['stage:b', 'stage:c']))
    await flush()
    off()
    expect(f.emittedEvents('unsubscribe')).toEqual([{ rooms: ['stage:c'] }])
    a()
    expect(f.emittedEvents('unsubscribe')[1]).toEqual({ rooms: ['stage:a', 'stage:b'] })
  })

  it('en cada (re)conexión emite subscribe y luego sync con todos los rooms', async () => {
    const f = createFakeSocket(okResponders)
    const rt = createQueueRealtime(f.socket)
    const s = sub(['stage:x'])
    rt.subscribe(s)
    f.fire('connect')
    await flush()
    f.fire('disconnect', 'transport close')
    f.fire('connect')
    await flush()
    expect(f.emitted.map((e) => e.event)).toEqual(['subscribe', 'sync', 'subscribe', 'sync'])
    expect(s.syncs).toHaveLength(2)
  })

  it('expone el estado de conexión', () => {
    const f = createFakeSocket()
    const rt = createQueueRealtime(f.socket)
    expect(rt.connected.value).toBe(false)
    f.fire('connect')
    expect([rt.connected.value, rt.reconnecting.value]).toEqual([true, false])
    f.fire('disconnect', 'transport close')
    expect([rt.connected.value, rt.reconnecting.value]).toEqual([false, true])
    f.fire('connect')
    expect([rt.connected.value, rt.reconnecting.value]).toEqual([true, false])
    f.fire('connect_error', new Error('x'))
    expect([rt.connected.value, rt.reconnecting.value]).toEqual([false, true])
  })

  it('reenvía los eventos del servidor a los suscriptores', () => {
    const f = createFakeSocket()
    const rt = createQueueRealtime(f.socket)
    const s = sub(['stage:x'])
    rt.subscribe(s)
    f.fire('sample:updated', { id: 'a', version: 2 })
    expect(s.events).toEqual([['sample:updated', { id: 'a', version: 2 }]])
  })

  it('un error de suscripción deja un mensaje legible y no sincroniza', async () => {
    const f = createFakeSocket({ subscribe: () => ({ ok: false, error: 'forbidden' }) })
    f.fire('connect')
    const rt = createQueueRealtime(f.socket)
    const s = sub(['stage:x'])
    rt.subscribe(s)
    await flush()
    expect(rt.error.value).toMatch(/permiso/)
    expect(s.syncs).toHaveLength(0)
  })

  it('sin ack del servidor reporta el fallo de sincronización', async () => {
    const f = createFakeSocket()
    f.socket.emit = () => {} // nunca responde
    f.fire('connect')
    const rt = createQueueRealtime(f.socket, { ackTimeoutMs: 5 })
    rt.subscribe(sub(['stage:x']))
    await new Promise((r) => setTimeout(r, 20))
    expect(rt.error.value).toBe(SYNC_FAILED_MESSAGE)
  })
})
