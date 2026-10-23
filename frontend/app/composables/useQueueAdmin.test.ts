import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushAll } from '~/testing/dom'

const fake = await vi.hoisted(async () => (await import('~/testing/fakeApi')).createFakeApi())
mockNuxtImport('useLeoAppApi', () => () => fake.client)

enableAutoUnmount(afterEach)

const page = (n: number, total = 45) => ({ items: [], page: n, page_size: 20, total })

beforeEach(() => {
  fake.reset()
  fake.routes['GET /queue-admin/priorities'] = page(1)
})

async function mountList() {
  let list!: ReturnType<typeof useQueueAdminList>
  await mountSuspended(defineComponent({
    setup() {
      list = useQueueAdminList('priorities')
      return () => h('div')
    }
  }))
  await flushAll()
  return list
}

describe('useQueueAdminList', () => {
  it('carga al montar y expone total', async () => {
    const list = await mountList()
    expect(fake.requests).toHaveBeenCalledWith('GET', '/queue-admin/priorities', { params: { page: 1, page_size: 20 }, signal: expect.any(AbortSignal) })
    expect(list.total.value).toBe(45)
  })

  it('cambiar de página pide esa página', async () => {
    const list = await mountList()
    list.page.value = 2
    await flushAll()
    expect(fake.requests).toHaveBeenLastCalledWith('GET', '/queue-admin/priorities', { params: { page: 2, page_size: 20 }, signal: expect.any(AbortSignal) })
  })

  it('buscar o filtrar vuelve a la página 1 con una sola petición', async () => {
    const list = await mountList()
    list.page.value = 3
    await flushAll()
    fake.requests.mockClear()
    list.search.value = '  alta '
    list.activeFilter.value = false
    await flushAll()
    expect(fake.requests).toHaveBeenCalledTimes(1)
    expect(fake.requests).toHaveBeenCalledWith('GET', '/queue-admin/priorities', {
      params: { page: 1, page_size: 20, q: 'alta', is_active: false },
      signal: expect.any(AbortSignal)
    })
    expect(list.page.value).toBe(1)
  })

  it('un error de carga queda legible, sin el texto crudo', async () => {
    fake.routes['GET /queue-admin/priorities'] = () => Promise.reject(new TypeError('Failed to fetch'))
    const list = await mountList()
    expect(list.loadError.value).toContain('No se pudo cargar el listado.')
    expect(list.loadError.value).not.toMatch(/fetch/i)
  })
})

describe('useQueueAdminApi', () => {
  it('usa los verbos y rutas del backend', async () => {
    const api = useQueueAdminApi('return-reasons')
    await api.create({ code: 'a', name: 'A' })
    await api.update('i1', { name: 'B' })
    await api.deactivate('i1', 'motivo')
    await api.activate('i1')
    expect(fake.bodies('POST', '/queue-admin/return-reasons')).toEqual([{ code: 'a', name: 'A' }])
    expect(fake.bodies('PATCH', '/queue-admin/return-reasons/i1')).toEqual([{ name: 'B' }])
    expect(fake.bodies('POST', '/queue-admin/return-reasons/i1/deactivate')).toEqual([{ reason: 'motivo' }])
    expect(fake.requests).toHaveBeenCalledWith('POST', '/queue-admin/return-reasons/i1/activate', expect.anything())
  })
})
