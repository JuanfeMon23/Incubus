import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushAll } from '~/testing/dom'
import { entry } from '~/testing/fixtures'
import { signInWith } from '~/testing/session'
import { TAGS } from '~/utils/tags'

const fake = await vi.hoisted(async () => (await import('~/testing/fakeApi')).createFakeApi())
const subscribed = vi.hoisted(() => [] as string[][])
mockNuxtImport('useApi', () => () => fake.api)
mockNuxtImport('useQueueSocket', () => () => ({
  subscribe: (sub: { rooms: string[] }) => {
    subscribed.push(sub.rooms)
    return () => {}
  }
}))

enableAutoUnmount(afterEach)

beforeEach(() => {
  fake.reset()
  subscribed.length = 0
  fake.routes['GET /queue'] = [entry('en_atencion_recepcion')]
})

const Harness = defineComponent({
  setup() {
    const { entries } = useQueueList(['pre_recepcion', 'en_atencion_recepcion'])
    return () => h('p', entries.value.map((e) => e.id).join(','))
  }
})

describe('useQueueList solo usa las etapas con view', () => {
  it('pide y se suscribe únicamente a las etapas cuyo view tiene el usuario', async () => {
    signInWith([TAGS.reception.view])
    const wrapper = await mountSuspended(Harness)
    await flushAll()
    expect(fake.requests).toHaveBeenCalledWith('GET', '/queue?status=en_atencion_recepcion', expect.anything())
    expect(subscribed.flat()).toEqual(['stage:en_atencion_recepcion'])
    expect(wrapper.text()).toBe('e1')
  })

  it('con ambos view pide las dos etapas', async () => {
    signInWith([TAGS.reception.view, TAGS.preReception.view])
    await mountSuspended(Harness)
    await flushAll()
    expect(fake.requests).toHaveBeenCalledWith(
      'GET',
      '/queue?status=pre_recepcion&status=en_atencion_recepcion',
      expect.anything()
    )
  })

  it('sin ningún view no pide nada ni se suscribe (el servidor respondería forbidden)', async () => {
    signInWith([TAGS.results.enter])
    const wrapper = await mountSuspended(Harness)
    await flushAll()
    expect(fake.requests).not.toHaveBeenCalled()
    expect(subscribed).toEqual([])
    expect(wrapper.text()).toBe('')
  })
})
