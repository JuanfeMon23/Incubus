import { describe, expect, it, vi } from 'vitest'
import type { QueueEntry } from '../types'
import { createFakeSocket } from '../testing/fakeSocket'
import { createQueueList, createQueueRefresh } from './queueList'
import { createQueueRealtime } from './queueRealtime'
import type { LiveEvent } from './queueLive'

const entry = (id: string, over: Partial<QueueEntry> = {}): QueueEntry => ({
  id,
  status: 'pre_recepcion',
  claimed_by: null,
  assigned_professional_id: null,
  assigned_professional_name: null,
  arrived_at: `2026-10-20T10:0${id.length}:00Z`,
  draft: {},
  patient: {} as QueueEntry['patient'],
  priority: { id: 'p1', code: 'media', name: 'Media', color_hex: '#000', rank: 2 },
  order_number: null,
  version: 1,
  ...over
})
const ev = (id: string, version: number, over: Partial<LiveEvent> = {}): LiveEvent => ({
  id,
  status: 'pre_recepcion',
  version,
  priority_id: 'p1',
  assigned_professional_id: null,
  order_number: null,
  ...over
})
const flush = () => new Promise((r) => setTimeout(r, 0))
const STAGES = ['pre_recepcion', 'en_atencion_recepcion'] as const

function setup(initial: QueueEntry[], remote: Record<string, QueueEntry> = {}) {
  const f = createFakeSocket({
    subscribe: () => ({ ok: true }),
    sync: () => ({ ok: true, entries: initial.map((e) => ({ id: e.id, status: e.status, version: e.version })) })
  })
  f.fire('connect')
  const rt = createQueueRealtime(f.socket)
  const fetchList = vi.fn(async (_s?: unknown) => initial)
  const fetchOne = vi.fn(async (id: string) => remote[id]!)
  const list = createQueueList([...STAGES], { subscribe: rt.subscribe, fetchList, fetchOne, toMessage: () => 'msg' })
  return { f, rt, list, fetchList, fetchOne }
}

describe('createQueueList', () => {
  it('carga por REST y se suscribe a los rooms de sus etapas', async () => {
    const { list, f, fetchList } = setup([entry('a')])
    await list.start()
    await flush()
    expect(list.entries.value.map((e) => e.id)).toEqual(['a'])
    expect(list.loading.value).toBe(false)
    expect(f.emittedEvents('subscribe')).toEqual([{ rooms: ['stage:pre_recepcion', 'stage:en_atencion_recepcion'] }])
    expect(fetchList).toHaveBeenCalledTimes(1) // el sync coincide: sin refetch
  })

  it('entry:created pide el detalle por REST solo de esa entrada', async () => {
    const { list, f, fetchOne, fetchList } = setup([entry('a')], { bb: entry('bb', { version: 5 }) })
    await list.start()
    f.fire('entry:created', ev('bb', 5))
    await flush()
    expect(fetchOne).toHaveBeenCalledWith('bb')
    expect(fetchList).toHaveBeenCalledTimes(1)
    expect(list.entries.value.map((e) => e.id).sort()).toEqual(['a', 'bb'])
  })

  it('status:changed dentro de mis etapas actualiza sin red y fuera de ellas retira', async () => {
    const { list, f, fetchOne } = setup([entry('a')])
    await list.start()
    f.fire('status:changed', ev('a', 2, { status: 'en_atencion_recepcion', previous_status: 'pre_recepcion' }))
    expect(list.entries.value[0]).toMatchObject({ status: 'en_atencion_recepcion', version: 2 })
    f.fire('status:changed', ev('a', 3, { status: 'en_espera_impresion', previous_status: 'en_atencion_recepcion' }))
    expect(list.entries.value).toEqual([])
    expect(fetchOne).not.toHaveBeenCalled()
  })

  it('entry:removed retira la entrada', async () => {
    const { list, f } = setup([entry('a')])
    await list.start()
    f.fire('entry:removed', ev('a', 2, { status: 'retirado', previous_status: 'pre_recepcion' }))
    expect(list.entries.value).toEqual([])
  })

  it('descarta eventos duplicados o fuera de orden por version', async () => {
    const { list, f } = setup([entry('a')])
    await list.start()
    f.fire('status:changed', ev('a', 4, { status: 'en_atencion_recepcion' }))
    f.fire('status:changed', ev('a', 3, { status: 'pre_recepcion' })) // viejo
    f.fire('status:changed', ev('a', 4, { status: 'pre_recepcion' })) // duplicado
    expect(list.entries.value[0]).toMatchObject({ status: 'en_atencion_recepcion', version: 4 })
    // retirada y luego un evento viejo no la resucita
    f.fire('status:changed', ev('a', 6, { status: 'en_espera_impresion' }))
    f.fire('status:changed', ev('a', 5, { status: 'pre_recepcion' }))
    expect(list.entries.value).toEqual([])
  })

  it('al reconectar con diferencias en el snapshot recarga la lista completa', async () => {
    const { list, f, fetchList } = setup([entry('a')])
    await list.start()
    await flush()
    fetchList.mockResolvedValueOnce([entry('a', { version: 7 })])
    f.fire('disconnect', 'transport close')
    f.socket.emit = ((event: string, ...a: any[]) => {
      const ack = a[a.length - 1]
      ack(event === 'sync' ? { ok: true, entries: [{ id: 'a', status: 'pre_recepcion', version: 7 }] } : { ok: true })
    }) as never
    f.fire('connect')
    await flush()
    await flush()
    expect(fetchList).toHaveBeenCalledTimes(2)
    expect(list.entries.value[0]!.version).toBe(7)
  })

  it('error de carga queda como mensaje legible', async () => {
    const { list, fetchList } = setup([])
    fetchList.mockRejectedValueOnce(new Error('raw'))
    await list.start()
    expect(list.error.value).toBe('msg')
  })

  it('stop() des-suscribe de los rooms', async () => {
    const { list, f } = setup([entry('a')])
    await list.start()
    await flush()
    list.stop()
    expect(f.emittedEvents('unsubscribe')).toEqual([{ rooms: ['stage:pre_recepcion', 'stage:en_atencion_recepcion'] }])
  })
})

describe('createQueueRefresh', () => {
  it('refresca con debounce ante ráfagas de sample:updated / status:changed / entry:updated', () => {
    vi.useFakeTimers()
    const f = createFakeSocket()
    const rt = createQueueRealtime(f.socket)
    const load = vi.fn()
    const r = createQueueRefresh(['en_laboratorio'], load, { subscribe: rt.subscribe, debounceMs: 100 })
    r.start()
    f.fire('sample:updated', ev('a', 2))
    f.fire('status:changed', ev('a', 3))
    f.fire('entry:updated', ev('a', 4))
    expect(load).not.toHaveBeenCalled()
    vi.advanceTimersByTime(100)
    expect(load).toHaveBeenCalledTimes(1)
    r.stop()
    vi.useRealTimers()
  })

  it('no refresca si está deshabilitado (modal abierto)', () => {
    vi.useFakeTimers()
    const f = createFakeSocket()
    const rt = createQueueRealtime(f.socket)
    const load = vi.fn()
    const r = createQueueRefresh(['en_laboratorio'], load, { subscribe: rt.subscribe, debounceMs: 10, enabled: () => false })
    r.start()
    f.fire('entry:updated', ev('a', 2))
    vi.advanceTimersByTime(50)
    expect(load).not.toHaveBeenCalled()
    vi.useRealTimers()
  })
})
