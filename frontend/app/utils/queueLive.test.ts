import { describe, expect, it } from 'vitest'
import type { QueueEntry } from '../types'
import { decideEvent, patchEntry, sampleToggleError, SAMPLING_CONFLICT_MESSAGE, snapshotDiffers, sortQueue } from './queueLive'
import type { LiveEvent } from './queueLive'

const entry = (over: Partial<QueueEntry> = {}): QueueEntry => ({
  id: 'a',
  status: 'pre_recepcion',
  claimed_by: null,
  assigned_professional_id: null,
  assigned_professional_name: null,
  arrived_at: '2026-10-20T10:00:00Z',
  draft: {},
  patient: {} as QueueEntry['patient'],
  priority: { id: 'p1', code: 'media', name: 'Media', color_hex: '#000', rank: 2 },
  order_number: null,
  version: 3,
  ...over
})
const ev = (over: Partial<LiveEvent> = {}): LiveEvent => ({
  id: 'a',
  status: 'pre_recepcion',
  version: 4,
  priority_id: 'p1',
  assigned_professional_id: null,
  order_number: null,
  ...over
})
const STAGES = ['pre_recepcion', 'en_atencion_recepcion'] as const

describe('decideEvent', () => {
  it('descarta eventos con versión menor o igual a la vista', () => {
    expect(decideEvent('status:changed', ev({ version: 3 }), entry(), 3, STAGES)).toBe('ignore')
    expect(decideEvent('status:changed', ev({ version: 2 }), entry(), 3, STAGES)).toBe('ignore')
  })
  it('pide el detalle de una entrada nueva de mi etapa', () => {
    expect(decideEvent('entry:created', ev(), undefined, undefined, STAGES)).toBe('fetch')
  })
  it('un cambio de estado dentro de mis etapas se aplica como parche', () => {
    expect(decideEvent('status:changed', ev({ status: 'en_atencion_recepcion' }), entry(), 3, STAGES)).toBe('patch')
  })
  it('retira la entrada que salió de mis etapas y ignora la que no conocía', () => {
    const out = ev({ status: 'en_espera_impresion', previous_status: 'en_atencion_recepcion' })
    expect(decideEvent('status:changed', out, entry(), 3, STAGES)).toBe('remove')
    expect(decideEvent('status:changed', out, undefined, undefined, STAGES)).toBe('ignore')
    expect(decideEvent('entry:removed', ev({ status: 'retirado' }), entry(), 3, STAGES)).toBe('remove')
  })
  it('pide el detalle si cambia algo que el evento no trae completo', () => {
    expect(decideEvent('entry:updated', ev(), entry(), 3, STAGES)).toBe('fetch')
    expect(decideEvent('status:changed', ev({ priority_id: 'p2' }), entry(), 3, STAGES)).toBe('fetch')
    expect(decideEvent('status:changed', ev({ assigned_professional_id: 'x' }), entry(), 3, STAGES)).toBe('fetch')
  })
  it('sample:updated solo sube la versión', () => {
    expect(decideEvent('sample:updated', ev({ sample_id: 's' }), entry(), 3, STAGES)).toBe('patch')
  })
})

describe('utilidades de la cola', () => {
  it('patchEntry conserva los datos que el evento no trae', () => {
    const p = patchEntry(entry(), ev({ status: 'en_atencion_recepcion', version: 9, order_number: 'X1' }))
    expect(p).toMatchObject({ status: 'en_atencion_recepcion', version: 9, order_number: 'X1', draft: {} })
  })
  it('sortQueue ordena por prioridad y luego por llegada', () => {
    const hi = entry({ id: 'h', priority: { ...entry().priority, rank: 1 }, arrived_at: '2026-10-20T11:00:00Z' })
    const old = entry({ id: 'o', arrived_at: '2026-10-20T09:00:00Z' })
    expect(sortQueue([entry(), hi, old]).map((e) => e.id)).toEqual(['h', 'o', 'a'])
  })
  it('snapshotDiffers detecta ids o versiones distintas', () => {
    expect(snapshotDiffers([entry()], [{ id: 'a', version: 3 }])).toBe(false)
    expect(snapshotDiffers([entry()], [{ id: 'a', version: 4 }])).toBe(true)
    expect(snapshotDiffers([entry()], [])).toBe(true)
    expect(snapshotDiffers([], [{ id: 'z', version: 1 }])).toBe(true)
  })
  it('un 409 al marcar un tubo da un mensaje legible; otros errores usan el fallback', () => {
    expect(sampleToggleError({ status: 409, data: { details: { status: 'toma_finalizada' } } }, () => 'x')).toBe(
      SAMPLING_CONFLICT_MESSAGE
    )
    expect(sampleToggleError({ statusCode: 500 }, () => 'fallback')).toBe('fallback')
  })
})
