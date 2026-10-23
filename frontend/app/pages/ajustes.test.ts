import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushAll } from '~/testing/dom'
import { signInWith } from '#leo-client/testing/session'
import { TAGS } from '~/utils/tags'
import SettingsPage from './ajustes.vue'

const fake = await vi.hoisted(async () => (await import('~/testing/fakeApi')).createFakeApi())
mockNuxtImport('useLeoAppApi', () => () => fake.client)

enableAutoUnmount(afterEach)

const setting = (over: Record<string, unknown>) => ({
  key: 'x', type: 'int', value: 10, default: 10, min: 1, max: 100, unit: null, description: 'X',
  version: 1, requires_security_permission: false, updated_at: null, updated_by: null, updated_by_username: null, ...over
})
const TIMEOUT = setting({ key: 'queue.timeout', description: 'Tiempo de espera', version: 3 })
const LOCKED = setting({ key: 'security.pin', description: 'Intentos de PIN', requires_security_permission: true })

beforeEach(() => {
  fake.reset()
  document.body.innerHTML = ''
  fake.routes['GET /settings'] = { groups: [{ group: 'Cola', settings: [TIMEOUT, LOCKED] }] }
})

async function mountPage(tags: string[]) {
  signInWith(tags)
  const wrapper = await mountSuspended(SettingsPage)
  await flushAll()
  return wrapper
}

const input = (wrapper: { element: Element }, key: string) =>
  wrapper.element.querySelector(`[data-key="${key}"] input`) as HTMLInputElement
const saveButton = (wrapper: { element: Element }, key: string) =>
  wrapper.element.querySelector(`[data-key="${key}"] [data-testid="setting-save"]`) as HTMLButtonElement
const dialog = () => document.querySelector('[role="dialog"]') as HTMLElement

async function type(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
  el.value = value
  el.dispatchEvent(new Event('input', { bubbles: true }))
  await flushAll()
}

describe('ajustes del sistema', () => {
  it('exige settings.view como metadato de ruta', () => {
    expect((useRouter().resolve('/ajustes').meta as { leo?: { tag?: string } }).leo?.tag).toBe(TAGS.settings.view)
  })

  it('lista los ajustes por grupo', async () => {
    const wrapper = await mountPage([TAGS.settings.view])
    expect(wrapper.text()).toContain('Cola')
    expect(wrapper.text()).toContain('Tiempo de espera')
  })

  it('solo con view es de solo lectura', async () => {
    const wrapper = await mountPage([TAGS.settings.view])
    expect(input(wrapper, 'queue.timeout').disabled).toBe(true)
    expect(wrapper.text()).toContain('No tienes permiso para modificar ajustes.')
  })

  it('con edit se edita lo común pero no lo de seguridad; edit-security lo habilita', async () => {
    const edit = await mountPage([TAGS.settings.view, TAGS.settings.edit])
    expect(input(edit, 'queue.timeout').disabled).toBe(false)
    expect(input(edit, 'security.pin').disabled).toBe(true)
    expect(edit.text()).toContain('Solo con permiso de seguridad.')

    const security = await mountPage([TAGS.settings.view, TAGS.settings.edit, TAGS.settings.editSecurity])
    expect(input(security, 'security.pin').disabled).toBe(false)
  })

  it('guardar pide motivo y envía value, reason y expected_version', async () => {
    fake.routes['PUT /settings/queue.timeout'] = ({ body }: any) => ({ ...TIMEOUT, value: body.value, version: 4 })
    const wrapper = await mountPage([TAGS.settings.view, TAGS.settings.edit])
    await type(input(wrapper, 'queue.timeout'), '20')
    saveButton(wrapper, 'queue.timeout').click()
    await flushAll()
    await type(dialog().querySelector('textarea')!, 'Más holgura')
    ;(dialog().querySelector('button[type="submit"]') as HTMLButtonElement).click()
    await flushAll()
    expect(fake.bodies('PUT', '/settings/queue.timeout')).toEqual([{ value: 20, reason: 'Más holgura', expected_version: 3 }])
  })

  it('un 422 por page_size al cargar muestra el mensaje legible del servidor con el máximo', async () => {
    fake.routes['GET /settings'] = () =>
      Promise.reject(new LeoApiError(422, 'validation_error', 'El tamaño de página máximo permitido es 50.', { field: 'page_size', max: 50 }))
    const wrapper = await mountPage([TAGS.settings.view])
    expect(wrapper.text()).toContain('máximo permitido es 50')
  })
})
