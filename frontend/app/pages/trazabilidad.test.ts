import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { findButton, flushAll } from '~/testing/dom'
import { signInWith } from '#leo-client/testing/session'
import { TAGS } from '~/utils/tags'
import TracePage from './trazabilidad.vue'

const fake = await vi.hoisted(async () => (await import('~/testing/fakeApi')).createFakeApi())
mockNuxtImport('useLeoAppApi', () => () => fake.client)

enableAutoUnmount(afterEach)

const TEST = { id: 't1', code: 'GLU', name: 'Glucosa', area_code: 'QUI', validation_status: 'draft', created_at: '2026-03-01T07:00:00' }
const TRACE = {
  order_number: 'O-1', order_id: 'o', test: TEST, page: 1, page_size: 50, total: 1,
  events: [{ at: '2026-03-01T08:00:00', step: 'sample.collected', scope: 'sample', actor: { id: null, name: null, staff_id: null }, summary: 'Tubo tomado', details: {}, source: 'event' }]
}

beforeEach(() => {
  fake.reset()
  document.body.innerHTML = ''
  try { localStorage.clear() } catch { /* sin almacenamiento */ }
  fake.routes['GET /orders/O-1/tests/t1/trace'] = TRACE
})

async function search(w: { element: Element }, value: string) {
  const input = w.element.querySelector('input') as HTMLInputElement
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushAll()
  w.element.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }))
  await flushAll()
}

describe('/trazabilidad', () => {
  it('varias pruebas: las lista y muestra la línea de tiempo al elegir una', async () => {
    signInWith([TAGS.results.trace])
    fake.routes['GET /orders/O-1/tests'] = { order_number: 'O-1', order_id: 'o', tests: [TEST, { ...TEST, id: 't2', code: 'HB', name: 'Hemoglobina' }] }
    const w = await mountSuspended(TracePage)
    await flushAll()
    expect(w.element.textContent).toContain('Busque una orden')
    expect(w.element.textContent).not.toContain('Profesional')
    await search(w, 'O-1')
    expect(w.element.textContent).toContain('GLU · Glucosa')
    expect(w.element.querySelector('[data-testid="trace-event"]')).toBeNull()
    findButton(w.element, 'GLU · Glucosa')!.click()
    await flushAll()
    expect(w.element.querySelectorAll('[data-testid="trace-event"]')).toHaveLength(1)
    expect(w.element.textContent).toContain('Sistema/servicio')
  })

  it('una sola prueba: se abre sola', async () => {
    signInWith([TAGS.results.trace])
    fake.routes['GET /orders/O-1/tests'] = { order_number: 'O-1', order_id: 'o', tests: [TEST] }
    const w = await mountSuspended(TracePage)
    await flushAll()
    await search(w, 'O-1')
    expect(w.element.querySelectorAll('[data-testid="trace-event"]')).toHaveLength(1)
  })

  it.each([['404 no existe'], ['403 sin permiso']])('error legible: %s', async (msg) => {
    signInWith([TAGS.results.trace])
    fake.routes['GET /orders/X-9/tests'] = () => { throw new Error(msg) }
    const w = await mountSuspended(TracePage)
    await flushAll()
    await search(w, 'X-9')
    expect(w.element.querySelector('[role="alert"]')).not.toBeNull()
  })
})
