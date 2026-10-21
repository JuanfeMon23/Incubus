import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { flushAll } from '~/testing/dom'
import { ALL, signInWith } from '~/testing/session'
import { TAGS } from '~/utils/tags'
import IndexPage from '../pages/index.vue'
import DefaultLayout from './default.vue'

mockNuxtImport('useQueueSocket', () => () => ({
  connected: { value: true },
  reconnecting: { value: false },
  error: { value: '' },
  subscribe: () => () => {},
  open: () => {},
  close: () => {}
}))

enableAutoUnmount(afterEach)

async function menuLabels(tags: string[]) {
  signInWith(tags)
  const wrapper = await mountSuspended(DefaultLayout)
  return wrapper.findAll('nav a').map((a) => a.text())
}

describe('menú lateral por permiso', () => {
  it('con todos los view aparecen las seis pantallas', async () => {
    expect(await menuLabels(ALL)).toEqual([
      'Pre-recepción',
      'Recepción',
      'Impresión de etiquetas',
      'Toma de muestras',
      'Recepción laboratorio',
      'Resultados'
    ])
  })

  it.each([
    [TAGS.preReception.view, 'Pre-recepción'],
    [TAGS.reception.view, 'Recepción'],
    [TAGS.labelPrinting.view, 'Impresión de etiquetas'],
    [TAGS.sampling.view, 'Toma de muestras'],
    [TAGS.labReception.view, 'Recepción laboratorio'],
    [TAGS.results.view, 'Resultados']
  ])('con solo %s aparece únicamente «%s»', async (tag, label) => {
    expect(await menuLabels([tag])).toEqual([label])
  })

  it('los permisos de acción no abren pantallas por sí solos', async () => {
    expect(await menuLabels([TAGS.preReception.enqueue, TAGS.results.validate, TAGS.resultsDelivery.view])).toEqual([])
  })

  it('el usuario y la app aparecen en la barra superior de Leo', async () => {
    signInWith([TAGS.reception.view])
    const wrapper = await mountSuspended(DefaultLayout)
    expect(wrapper.find('[data-testid="leo-current-app"]').text()).toBe('Incubus')
    expect(wrapper.text()).toContain('Ana Pérez')
  })
})

describe('inicio', () => {
  it('con varias etapas ofrece elegir entre las que tiene', async () => {
    signInWith([TAGS.reception.view, TAGS.results.view])
    const wrapper = await mountSuspended(IndexPage)
    await flushAll()
    expect(wrapper.text()).toContain('¿A qué etapa vas a entrar?')
    expect(wrapper.findAll('a').map((a) => a.text())).toEqual([
      expect.stringContaining('Recepción'),
      expect.stringContaining('Resultados')
    ])
  })

  it('sin ninguna etapa explica que falta asignar un rol', async () => {
    signInWith([TAGS.results.enter])
    const wrapper = await mountSuspended(IndexPage)
    await flushAll()
    expect(wrapper.text()).toContain('aún no tiene pantallas asignadas')
  })
})
