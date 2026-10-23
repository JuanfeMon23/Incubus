import { describe, expect, it } from 'vitest'
import type { TraceEvent } from '../types'
import { actorName, CATEGORY_INFO, detailLines, filterEvents, groupByDay, isQueueStep, stepCategory, stepLabel, timeLabel } from './trace'

const ev = (step: string, at: string, over: Partial<TraceEvent> = {}): TraceEvent => ({
  at, step, scope: 'test', actor: { id: null, name: null, staff_id: null }, summary: step, details: {}, source: 'event', ...over
})
// Fechas locales (sin zona) para no depender del huso del entorno.
const local = (d: string) => new Date(d).toISOString()

describe('stepCategory', () => {
  it.each([
    ['queue.entered', 'queue'],
    ['queue.reception_claimed', 'reception'],
    ['queue.reception_closed', 'reception'],
    ['queue.labels_printed', 'labels'],
    ['queue.sampling_finished', 'sampling'],
    ['queue.in_laboratory', 'lab'],
    ['labels.printed', 'labels'],
    ['sample.collected', 'sampling'],
    ['lab.received', 'lab'],
    ['precondition.checked', 'sampling'],
    ['result.changed', 'capture'],
    ['test.validated', 'validation'],
    ['delivery.report_downloaded', 'delivery'],
    ['activation.used', 'activation'],
    ['order.finalized', 'order'],
    ['algo.nuevo', 'order']
  ])('%s -> %s', (step, cat) => {
    expect(stepCategory(step)).toBe(cat)
    expect(CATEGORY_INFO[cat as keyof typeof CATEGORY_INFO].icon).toBeTruthy()
  })
  it('etiqueta legible y fallback al paso', () => {
    expect(stepLabel('result.entered')).toBe('Resultado capturado')
    expect(stepLabel('x.y')).toBe('x.y')
    expect(isQueueStep('queue.removed')).toBe(true)
    expect(isQueueStep('lab.received')).toBe(false)
  })
})

describe('actorName', () => {
  it('usa el nombre o «Sistema/servicio»', () => {
    expect(actorName({ id: 'u', name: ' Ana ', staff_id: null })).toBe('Ana')
    expect(actorName({ id: null, name: null, staff_id: null })).toBe('Sistema/servicio')
    expect(actorName({ id: 'svc', name: '', staff_id: null })).toBe('Sistema/servicio')
  })
})

describe('groupByDay', () => {
  it('agrupa por día local y conserva el orden', () => {
    const a = ev('a', local('2026-03-01T08:00:00'))
    const b = ev('b', local('2026-03-01T23:59:00'))
    const c = ev('c', local('2026-03-02T00:01:00'))
    const days = groupByDay([a, b, c])
    expect(days.map((d) => d.key)).toEqual(['2026-03-01', '2026-03-02'])
    expect(days[0]!.events).toEqual([a, b])
    expect(days[1]!.events).toEqual([c])
    expect(groupByDay([])).toEqual([])
  })
  it('hora local HH:MM:SS', () => {
    expect(timeLabel(local('2026-03-01T08:05:09'))).toBe('08:05:09')
  })
})

describe('filterEvents', () => {
  const list = [
    ev('queue.entered', local('2026-03-01T08:00:00'), { scope: 'order' }),
    ev('sample.collected', local('2026-03-01T09:00:00'), { scope: 'sample' }),
    ev('result.entered', local('2026-03-01T10:00:00'), { scope: 'test' })
  ]
  it('por ámbito', () => {
    expect(filterEvents(list, { scopes: ['test'], hideQueue: false }).map((e) => e.step)).toEqual(['result.entered'])
    expect(filterEvents(list, { scopes: ['test', 'order', 'sample'], hideQueue: false })).toHaveLength(3)
    expect(filterEvents(list, { scopes: [], hideQueue: false })).toHaveLength(0)
  })
  it('oculta los pasos de cola', () => {
    expect(filterEvents(list, { scopes: ['test', 'order', 'sample'], hideQueue: true }).map((e) => e.step)).toEqual(['sample.collected', 'result.entered'])
  })
})

describe('detailLines', () => {
  it('captura: anterior -> nuevo con bandera y calculado', () => {
    expect(detailLines(ev('result.changed', 'x', { details: { analyte_code: 'GLU', before: 90, after: 130, flag: 'H', calculated: false } }))).toEqual(['GLU: 90 → 130 (bandera H)'])
    expect(detailLines(ev('result.entered', 'x', { details: { analyte_code: 'IMC', before: null, after: '22', flag: null, calculated: true } }))).toEqual(['IMC: — → 22 · calculado'])
    expect(detailLines(ev('result.cleared', 'x', { details: { analyte_code: 'GLU', before: 5, after: null } }))).toEqual(['GLU: 5 → —'])
  })
  it('precondición con antes/después y nota', () => {
    const lines = detailLines(ev('precondition.checked', 'x', {
      details: { stage: 'sampling', key: 'ayuno', name: 'Ayuno', before: null, after: { met: false, note: 'comió' } }
    }))
    expect(lines).toEqual(['Ayuno (Toma de muestras): Sin registrar → No cumplida — comió'])
  })
  it('precondición derivada', () => {
    expect(detailLines(ev('precondition.checked', 'x', { details: { stage: 'reception', checked: 3, unmet_keys: ['ayuno'] } }))).toEqual(['Recepción: 3 verificadas', 'No cumplidas: ayuno'])
    expect(detailLines(ev('precondition.checked', 'x', { details: { stage: 'reception', checked: 2, unmet_keys: [] } }))[1]).toBe('Todas cumplidas')
  })
  it('validación', () => {
    expect(detailLines(ev('test.validated', 'x', { details: { abnormal_flags: [{ analyte_code: 'GLU', flag: 'H' }], validated_by: 'Dra. Pérez' } }))).toEqual(['Banderas anormales: GLU H', 'Firmado por: Dra. Pérez'])
    expect(detailLines(ev('test.validated', 'x', { details: { abnormal_flags: [] } }))).toEqual(['Sin banderas anormales'])
  })
  it('otros pasos o details vacíos no tienen líneas', () => {
    expect(detailLines(ev('lab.received', 'x'))).toEqual([])
    expect(detailLines(ev('result.entered', 'x'))).toEqual([])
  })
})
