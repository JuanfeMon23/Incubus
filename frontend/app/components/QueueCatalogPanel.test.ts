import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { findButton, flushAll } from '~/testing/dom'
import { signInWith } from '#leo-client/testing/session'
import { ALL, allExcept } from '~/testing/session'
import type { QueueAdminKind } from '~/types'
import { TAGS } from '~/utils/tags'
import QueueCatalogPanel from './QueueCatalogPanel.vue'

const fake = await vi.hoisted(async () => (await import('~/testing/fakeApi')).createFakeApi())
mockNuxtImport('useLeoAppApi', () => () => fake.client)

enableAutoUnmount(afterEach)

const row = (over: Record<string, unknown>) => ({
  id: 'x', code: 'x', name: 'X', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T10:00:00Z',
  color_hex: '#336699', rank: 1, ...over
})
const MEDIA = row({ id: 'm', code: 'media', name: 'Media', rank: 2 })
const URGENTE = row({ id: 'u', code: 'urgente', name: 'Urgente', rank: 1 })
const BAJA = row({ id: 'b', code: 'baja', name: 'Baja', rank: 3, is_active: false })

beforeEach(() => {
  fake.reset()
  document.body.innerHTML = ''
  fake.routes['GET /queue-admin/priorities'] = { items: [URGENTE, MEDIA, BAJA], page: 1, page_size: 20, total: 3 }
})

async function mountPanel(tags: string[], kind: QueueAdminKind = 'priorities') {
  signInWith(tags)
  const wrapper = await mountSuspended(QueueCatalogPanel, { props: { kind } })
  await flushAll()
  return wrapper
}

const dialog = () => document.querySelector('[role="dialog"]') as HTMLElement
const rowButton = (wrapper: { element: Element }, label: string) =>
  wrapper.element.querySelector(`button[aria-label="${label}"]`) as HTMLButtonElement | null
const submitButton = () => dialog().querySelector('button[type="submit"]') as HTMLButtonElement

async function type(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushAll()
}

describe('QueueCatalogPanel · permisos por botón', () => {
  it('solo con view se ve la tabla pero ningún botón de acción', async () => {
    const wrapper = await mountPanel([TAGS.queueAdmin.view])
    expect(wrapper.text()).toContain('Urgente')
    expect(findButton(wrapper.element, 'Nueva prioridad')).toBeNull()
    expect(rowButton(wrapper, 'Editar Urgente')).toBeNull()
    expect(rowButton(wrapper, 'Desactivar Urgente')).toBeNull()
    expect(rowButton(wrapper, 'Reactivar Baja')).toBeNull()
  })

  it.each(['create', 'update', 'toggle'] as const)('cada tag habilita solo lo suyo: %s', async (verb) => {
    const wrapper = await mountPanel([TAGS.queueAdmin.view, TAGS.queueAdmin[verb]])
    expect(!!findButton(wrapper.element, 'Nueva prioridad')).toBe(verb === 'create')
    expect(!!rowButton(wrapper, 'Editar Urgente')).toBe(verb === 'update')
    expect(!!rowButton(wrapper, 'Desactivar Urgente')).toBe(verb === 'toggle')
    expect(!!rowButton(wrapper, 'Reactivar Baja')).toBe(verb === 'toggle')
  })

  it('sin create no hay botón de crear aunque tenga el resto', async () => {
    const wrapper = await mountPanel(allExcept(TAGS.queueAdmin.create))
    expect(findButton(wrapper.element, 'Nueva prioridad')).toBeNull()
  })

  it('pide la lista con page y page_size y muestra el chip de color', async () => {
    const wrapper = await mountPanel(ALL)
    expect(fake.requests).toHaveBeenCalledWith('GET', '/queue-admin/priorities', { params: { page: 1, page_size: 20 } })
    expect(wrapper.find('span[style*="background-color"]').exists()).toBe(true)
  })

  it('en motivos el botón dice «Nuevo motivo de retiro» y no hay columna de orden', async () => {
    fake.routes['GET /queue-admin/removal-reasons'] = {
      items: [row({ code: 'duplicado', name: 'Duplicado', color_hex: null, rank: null })], page: 1, page_size: 20, total: 1
    }
    const wrapper = await mountPanel(ALL, 'removal-reasons')
    expect(findButton(wrapper.element, 'Nuevo motivo de retiro')).not.toBeNull()
    expect(wrapper.text()).not.toContain('Orden')
  })
})

describe('QueueCatalogPanel · desactivar y reactivar', () => {
  it('«media» no se puede desactivar: botón deshabilitado con la explicación', async () => {
    const wrapper = await mountPanel(ALL)
    const media = rowButton(wrapper, 'Desactivar Media')!
    expect(media.disabled).toBe(true)
    expect(media.closest('[title]')?.getAttribute('title')).toMatch(/no se puede desactivar/)
    expect(rowButton(wrapper, 'Desactivar Urgente')!.disabled).toBe(false)
  })

  it('exige motivo y lo envía en el POST', async () => {
    const wrapper = await mountPanel(ALL)
    rowButton(wrapper, 'Desactivar Urgente')!.click()
    await flushAll()
    submitButton().click()
    await flushAll()
    expect(dialog().textContent).toContain('El motivo es obligatorio.')
    expect(fake.requests).not.toHaveBeenCalledWith('POST', '/queue-admin/priorities/u/deactivate', expect.anything())

    await type(dialog().querySelector('textarea')!, 'Ya no se usa')
    submitButton().click()
    await flushAll()
    expect(fake.bodies('POST', '/queue-admin/priorities/u/deactivate')).toEqual([{ reason: 'Ya no se usa' }])
    expect(dialog()).toBeNull()
  })

  it('un 409 se muestra legible dentro del modal y no lo cierra', async () => {
    fake.routes['POST /queue-admin/priorities/u/deactivate'] = () =>
      Promise.reject(new LeoApiError(409, 'conflict', 'No se puede desactivar la última prioridad activa.', null))
    const wrapper = await mountPanel(ALL)
    rowButton(wrapper, 'Desactivar Urgente')!.click()
    await flushAll()
    await type(dialog().querySelector('textarea')!, 'x')
    submitButton().click()
    await flushAll()
    expect(dialog().textContent).toContain('No se puede desactivar la última prioridad activa.')
  })

  it('reactivar pide confirmación y luego llama a activate', async () => {
    const wrapper = await mountPanel(ALL)
    rowButton(wrapper, 'Reactivar Baja')!.click()
    await flushAll()
    expect(dialog().textContent).toContain('«Baja» volverá a estar activo.')
    expect(fake.requests).not.toHaveBeenCalledWith('POST', '/queue-admin/priorities/b/activate', expect.anything())
    findButton(dialog(), 'Reactivar')!.click()
    await flushAll()
    expect(fake.requests).toHaveBeenCalledWith('POST', '/queue-admin/priorities/b/activate', expect.anything())
  })
})

describe('QueueCatalogPanel · crear y editar', () => {
  it('un orden repetido (409) explica cómo intercambiar, sin el texto crudo', async () => {
    fake.routes['PATCH /queue-admin/priorities/u'] = () =>
      Promise.reject(new LeoApiError(409, 'conflict', 'crudo', { field: 'rank', value: 2 }))
    const wrapper = await mountPanel(ALL)
    rowButton(wrapper, 'Editar Urgente')!.click()
    await flushAll()
    expect(dialog().textContent).toContain('El código no se puede cambiar')
    await type(dialog().querySelector('input[type="number"]')!, '2')
    submitButton().click()
    await flushAll()
    expect(fake.bodies('PATCH', '/queue-admin/priorities/u')).toEqual([{ rank: 2 }])
    expect(dialog().textContent).toContain('orden libre')
    expect(dialog().textContent).not.toContain('crudo')
  })

  it('crear valida el code antes de enviar', async () => {
    const wrapper = await mountPanel(ALL)
    findButton(wrapper.element, 'Nueva prioridad')!.click()
    await flushAll()
    await type(dialog().querySelector('input[type="text"]')!, 'Mal Code')
    submitButton().click()
    await flushAll()
    expect(dialog().textContent).toContain('Usa minúsculas')
    expect(fake.requests).not.toHaveBeenCalledWith('POST', '/queue-admin/priorities', expect.anything())
  })
})
