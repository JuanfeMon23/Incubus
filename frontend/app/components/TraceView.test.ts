import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { findButton, flushAll } from '~/testing/dom'
import { signInWith } from '#leo-client/testing/session'
import { ALL, allExcept } from '~/testing/session'
import { TAGS } from '~/utils/tags'
import TraceButton from './TraceButton.vue'
import TraceTimeline from './TraceTimeline.vue'
import TraceView from './TraceView.vue'

const fake = await vi.hoisted(async () => (await import('~/testing/fakeApi')).createFakeApi())
mockNuxtImport('useLeoAppApi', () => () => fake.client)

enableAutoUnmount(afterEach)

const actor = { id: 'u1', name: 'Marta Ruiz', staff_id: null }
const none = { id: null, name: null, staff_id: null }
const E = (over: Record<string, unknown>) => ({
  at: '2026-03-01T08:00:00', step: 'queue.entered', scope: 'order', actor: none, summary: 'Ingresó a la cola', details: {}, source: 'event', ...over
})
const EVENTS = [
  E({}),
  E({ at: '2026-03-01T09:00:00', step: 'sample.collected', scope: 'sample', actor, summary: 'Tubo tomado' }),
  E({ at: '2026-03-02T10:00:00', step: 'result.changed', scope: 'test', actor, summary: 'Resultado modificado', details: { analyte_code: 'GLU', before: 90, after: 130, flag: 'H', calculated: false } }),
  E({ at: '2026-03-02T11:00:00', step: 'lab.received', scope: 'sample', summary: 'Recibido', source: 'derived' })
]
const TEST = { id: 't1', code: 'GLU', name: 'Glucosa', area_code: 'QUI', validation_status: 'draft', created_at: '2026-03-01T07:00:00' }
const page = (events: unknown[], total = events.length, p = 1) => ({ order_number: 'O-1', order_id: 'o', test: TEST, events, page: p, page_size: 50, total })
const ROUTE = 'GET /orders/O-1/tests/t1/trace'

beforeEach(() => {
  fake.reset()
  document.body.innerHTML = ''
})

async function mountView() {
  const w = await mountSuspended(TraceView, { props: { orderNumber: 'O-1', testId: 't1' } })
  await flushAll()
  return w
}
const rows = (w: { element: Element }) => [...w.element.querySelectorAll('[data-testid="trace-event"]')]

describe('TraceView', () => {
  it('agrupa por día, muestra actor legible, detalles y etiqueta «reconstruido»', async () => {
    fake.routes[ROUTE] = page(EVENTS)
    const w = await mountView()
    expect(w.element.querySelectorAll('section[aria-label]')).toHaveLength(2)
    expect(rows(w)).toHaveLength(4)
    const text = w.element.textContent ?? ''
    expect(text).toContain('Sistema/servicio')
    expect(text).toContain('Marta Ruiz')
    expect(text).toContain('GLU: 90 → 130 (bandera H)')
    const derived = [...w.element.querySelectorAll('[title]')].filter((el) => el.textContent?.trim() === 'Reconstruido')
    expect(derived).toHaveLength(1)
    expect(derived[0]!.getAttribute('title')).toBe('Datos anteriores a la trazabilidad detallada')
  })

  it('oculta pasos de cola y filtra por ámbito', async () => {
    fake.routes[ROUTE] = page(EVENTS)
    const w = await mountView()
    const boxes = [...w.element.querySelectorAll('input[type="checkbox"]')] as HTMLInputElement[]
    const labelOf = (b: HTMLInputElement) => b.closest('label')?.textContent?.trim()
    const click = async (label: string) => {
      const box = boxes.find((b) => labelOf(b) === label)!
      box.checked = !box.checked
      box.dispatchEvent(new Event('change', { bubbles: true }))
      await flushAll()
    }
    await click('Ocultar pasos de cola')
    expect(rows(w)).toHaveLength(3)
    await click('Tubo')
    expect(rows(w)).toHaveLength(1)
    await click('Prueba')
    expect(w.element.textContent).toContain('Ningún evento coincide con los filtros.')
  })

  it('carga más con la siguiente página', async () => {
    fake.routes[ROUTE] = (o: any) => (o.query.page === 1 ? page(EVENTS.slice(0, 2), 4, 1) : page(EVENTS.slice(2), 4, 2))
    const w = await mountView()
    expect(rows(w)).toHaveLength(2)
    findButton(w.element, 'Cargar más')!.click()
    await flushAll()
    expect(rows(w)).toHaveLength(4)
    expect(findButton(w.element, 'Cargar más')).toBeNull()
  })

  it('estado vacío y error legible', async () => {
    fake.routes[ROUTE] = page([])
    expect((await mountView()).element.textContent).toContain('aún no tiene eventos')
    fake.routes[ROUTE] = () => { throw new Error('boom') }
    const w = await mountView()
    expect(w.element.querySelector('[role="alert"]')).not.toBeNull()
    expect(w.element.textContent).not.toContain('boom')
  })
})

describe('TraceTimeline', () => {
  it('muestra cargando sin eventos', async () => {
    const w = await mountSuspended(TraceTimeline, { props: { events: [], loading: true } })
    expect(w.element.querySelector('[role="status"], svg, .animate-spin')).not.toBeNull()
  })
})

describe('TraceButton · permiso', () => {
  it('solo con results.trace aparece «Ver trazabilidad» y abre la vista', async () => {
    fake.routes[ROUTE] = page(EVENTS)
    signInWith(allExcept(TAGS.results.trace))
    const hidden = await mountSuspended(TraceButton, { props: { orderNumber: 'O-1', testId: 't1' } })
    await flushAll()
    expect(hidden.findAll('button')).toHaveLength(0)

    signInWith(ALL)
    const w = await mountSuspended(TraceButton, { props: { orderNumber: 'O-1', testId: 't1' } })
    await flushAll()
    expect(w.find('button').text()).toBe('Ver trazabilidad')
    await w.find('button').trigger('click')
    await flushAll()
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Glucosa')
  })
})
