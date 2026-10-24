import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import type { NuxtError } from '#app'
import { afterEach, describe, expect, it } from 'vitest'
// Incubus no tiene app/error.vue: Nuxt usa el de la capa Andromeda.
import ErrorPage from 'andromeda/app/error.vue'

enableAutoUnmount(afterEach)

describe('error.vue de la capa Andromeda', () => {
  it('404: texto fijo en español y acción de volver al inicio', async () => {
    const wrapper = await mountSuspended(ErrorPage, {
      props: { error: { statusCode: 404, message: 'Page not found: /x' } as NuxtError }
    })
    expect(wrapper.text()).toContain('No encontramos esta página')
    expect(wrapper.text()).toContain('Volver al inicio')
  })

  it('503: texto fijo, acción de reintentar y sin mensaje del servidor', async () => {
    const wrapper = await mountSuspended(ErrorPage, {
      props: { error: { statusCode: 503, message: 'upstream connect error' } as NuxtError }
    })
    expect(wrapper.text()).toContain('Servicio no disponible')
    expect(wrapper.text()).toContain('Reintentar')
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  })
})
