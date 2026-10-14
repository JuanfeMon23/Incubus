import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import PreconditionChecklist from './PreconditionChecklist.vue'

enableAutoUnmount(afterEach)

const items = [
  { key: 'ayuno:duration', name: 'Ayuno', duration_value: 8, duration_unit: 'horas', patient_instructions: 'Solo agua' },
  { key: 'tabaco:duration', name: 'No fumar', duration_value: 2, duration_unit: 'horas', patient_instructions: null }
]

describe('PreconditionChecklist', () => {
  it('muestra cada preanalítico con su duración', async () => {
    const wrapper = await mountSuspended(PreconditionChecklist, {
      props: { title: 'Verifique', items, modelValue: {} }
    })
    expect(wrapper.text()).toContain('Ayuno')
    expect(wrapper.text()).toContain('8 h')
    expect(wrapper.text()).toContain('No fumar')
  })

  it('emite la respuesta al pulsar Cumple / No cumple', async () => {
    const wrapper = await mountSuspended(PreconditionChecklist, {
      props: { title: 'Verifique', items, modelValue: {} }
    })
    const buttons = wrapper.findAll('button')
    await buttons[0]!.trigger('click') // Cumple del primero
    const first = wrapper.emitted('update:modelValue')![0]![0] as Record<string, { met: boolean }>
    expect(first['ayuno:duration']!.met).toBe(true)

    await buttons[1]!.trigger('click') // No cumple del primero
    const second = wrapper.emitted('update:modelValue')![1]![0] as Record<string, { met: boolean }>
    expect(second['ayuno:duration']!.met).toBe(false)
  })

  it('pide nota cuando no cumple y muestra el resultado de recepción', async () => {
    const wrapper = await mountSuspended(PreconditionChecklist, {
      props: {
        title: 'Verifique',
        items,
        modelValue: { 'ayuno:duration': { met: false, note: '' } },
        previous: { 'ayuno:duration': true }
      }
    })
    expect(wrapper.find('input').exists()).toBe(true)
    expect(wrapper.text()).toContain('Recepción: cumple')
  })
})
