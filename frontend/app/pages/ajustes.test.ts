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
const row = (wrapper: { element: Element }, key: string) => wrapper.element.querySelector(`[data-key="${key}"]`) as HTMLElement
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
    expect(input(wrapper, 'queue.timeout')).toBeNull()
    expect(wrapper.text()).toContain('No tienes permiso para modificar ajustes.')
  })

  it('sin incubus.settings.edit no hay controles de edición y el valor se muestra como texto', async () => {
    fake.routes['GET /settings'] = { groups: [{ group: 'Cola', settings: [TIMEOUT, setting({ key: 'queue.flag', type: 'bool', value: true, default: false, description: 'Aviso' })] }] }
    const wrapper = await mountPage([TAGS.settings.view])
    for (const key of ['queue.timeout', 'queue.flag']) {
      const el = row(wrapper, key)
      expect(el.querySelector('input, textarea, [role="switch"]')).toBeNull()
      expect(el.querySelector('[data-testid="setting-save"]')).toBeNull()
      expect(el.querySelector('[data-testid="setting-reset"]')).toBeNull()
      expect(el.querySelector('[data-testid="setting-history"]')).not.toBeNull()
    }
    expect(row(wrapper, 'queue.timeout').querySelector('[data-testid="setting-readonly"]')!.textContent).toContain('10')
  })

  it('con edit se edita lo común; lo de seguridad es texto sin controles hasta tener edit-security', async () => {
    const edit = await mountPage([TAGS.settings.view, TAGS.settings.edit])
    expect(input(edit, 'queue.timeout').disabled).toBe(false)
    expect(input(edit, 'security.pin')).toBeNull()
    const locked = row(edit, 'security.pin')
    expect(locked.querySelector('[data-testid="setting-save"]')).toBeNull()
    expect(locked.querySelector('[data-testid="setting-reset"]')).toBeNull()
    expect(locked.querySelector('[data-testid="setting-readonly"]')!.textContent).toContain('10')
    expect(locked.querySelector('[data-testid="setting-locked"]')).not.toBeNull()
    expect(edit.text()).toContain('Solo con permiso de seguridad.')

    const security = await mountPage([TAGS.settings.view, TAGS.settings.edit, TAGS.settings.editSecurity])
    expect(input(security, 'security.pin').disabled).toBe(false)
    expect(row(security, 'security.pin').querySelector('[data-testid="setting-save"]')).not.toBeNull()
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
