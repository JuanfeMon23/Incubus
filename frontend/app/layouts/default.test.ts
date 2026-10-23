import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushAll } from '~/testing/dom'
import { signInWith } from '#leo-client/testing/session'
import { ALL } from '~/testing/session'
import { TAGS } from '~/utils/tags'
import IndexPage from '../pages/index.vue'
import DefaultLayout from './default.vue'

const navigateToMock = vi.hoisted(() => vi.fn())
mockNuxtImport('navigateTo', () => navigateToMock)
mockNuxtImport('useQueueSocket', () => () => ({
  connected: { value: true },
  reconnecting: { value: false },
  error: { value: '' },
  subscribe: () => () => {},
  open: () => {},
  close: () => {}
}))

enableAutoUnmount(afterEach)
beforeEach(() => navigateToMock.mockClear())

async function menuLabels(tags: string[]) {
  signInWith(tags)
  const wrapper = await mountSuspended(DefaultLayout)
  return wrapper.findAll('nav a').map((a) => a.text())
}

describe('menú lateral por permiso', () => {
  it('con todos los view aparecen las nueve pantallas', async () => {
    expect(await menuLabels(ALL)).toEqual([
      'Pre-recepción',
      'Recepción',
      'Impresión de etiquetas',
      'Toma de muestras',
      'Recepción laboratorio',
      'Resultados',
      'Trazabilidad',
      'Catálogos de la cola',
      'Ajustes del sistema'
    ])
  })

  it.each([
    [TAGS.preReception.view, 'Pre-recepción'],
    [TAGS.reception.view, 'Recepción'],
    [TAGS.labelPrinting.view, 'Impresión de etiquetas'],
    [TAGS.sampling.view, 'Toma de muestras'],
    [TAGS.labReception.view, 'Recepción laboratorio'],
    [TAGS.results.view, 'Resultados'],
    [TAGS.results.trace, 'Trazabilidad'],
    [TAGS.queueAdmin.view, 'Catálogos de la cola'],
    [TAGS.settings.view, 'Ajustes del sistema']
  ])('con solo %s aparece únicamente «%s»', async (tag, label) => {
    expect(await menuLabels([tag])).toEqual([label])
  })

  it('los permisos de acción no abren pantallas por sí solos', async () => {
    expect(await menuLabels([TAGS.preReception.enqueue, TAGS.results.validate, TAGS.resultsDelivery.view, TAGS.queueAdmin.create, TAGS.queueAdmin.update, TAGS.queueAdmin.toggle, TAGS.settings.edit, TAGS.settings.editSecurity])).toEqual([])
  })

  it('el usuario y la app aparecen en la barra superior de Leo', async () => {
    signInWith([TAGS.reception.view])
    const wrapper = await mountSuspended(DefaultLayout)
    expect(wrapper.find('[data-testid="leo-current-app"]').text()).toBe('Incubus')
    expect(wrapper.text()).toContain('Ana Pérez')
  })
})

describe('inicio', () => {
  it.each([
    [[TAGS.sampling.view], '/toma-muestras'],
    [[TAGS.reception.view, TAGS.results.view], '/recepcion'],
    [ALL, '/pre-recepcion']
  ])('con %j redirige con replace al primer módulo', async (tags, route) => {
    signInWith(tags)
    await mountSuspended(IndexPage)
    await flushAll()
    expect(navigateToMock).toHaveBeenCalledTimes(1)
    expect(navigateToMock).toHaveBeenCalledWith(route, { replace: true })
  })

  it('sin ninguna pantalla explica que falta un rol y no redirige', async () => {
    signInWith([TAGS.results.enter])
    const wrapper = await mountSuspended(IndexPage)
    await flushAll()
    expect(navigateToMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(
      'Tu usuario no tiene acceso a ninguna pantalla de Incubus. Pide a un administrador de Leo que te asigne un rol.'
    )
  })

  it('no muestra el selector de etapas', async () => {
    signInWith([TAGS.reception.view, TAGS.results.view])
    const wrapper = await mountSuspended(IndexPage)
    await flushAll()
    expect(wrapper.text()).not.toContain('¿A qué etapa vas a entrar?')
    expect(wrapper.findAll('a')).toEqual([])
  })
})
