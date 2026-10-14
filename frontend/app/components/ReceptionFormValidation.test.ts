import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import UiFormField from '#andromeda/components/ui/UiFormField.vue'
import UiTextInput from '#andromeda/components/ui/UiTextInput.vue'
import { useZodForm } from '#andromeda/composables/useZodForm'
import { receptionPatientSchema } from '../utils/patientSchemas'

enableAutoUnmount(afterEach)

// Mismo cableado que la vista de recepción: useZodForm + UiFormField por nombre.
const Harness = defineComponent({
  setup() {
    const form = useZodForm(receptionPatientSchema, {
      initialValues: () => ({
        first_name: '', second_name: '', first_last_name: '', second_last_name: '',
        birth_date: '', birth_place: '', sex: '', blood_type: '', email: '',
        phone: '', insurer: '', address: ''
      })
    })
    const onSubmit = form.submit(async () => {})
    return () =>
      h('form', { onSubmit: (e: Event) => { e.preventDefault(); void onSubmit() } }, [
        h(UiFormField, { name: 'first_name', label: 'Primer nombre', required: true }, {
          default: () => h(UiTextInput)
        }),
        h(UiFormField, { name: 'email', label: 'Correo electrónico', required: true }, {
          default: () => h(UiTextInput)
        }),
        h('button', { type: 'submit' }, 'Guardar')
      ])
  }
})

describe('validación inline del formulario de recepción', () => {
  it('muestra el texto de campo obligatorio bajo cada campo vacío al enviar', async () => {
    const wrapper = await mountSuspended(Harness)
    await wrapper.find('form').trigger('submit')
    await new Promise((r) => setTimeout(r, 50))
    await nextTick()
    const text = wrapper.text()
    expect(text).toContain('El primer nombre es obligatorio.')
    expect(text).toContain('El correo electrónico es obligatorio.')
  })

  it('marca el campo como inválido (aria-invalid) y en rojo', async () => {
    const wrapper = await mountSuspended(Harness)
    await wrapper.find('form').trigger('submit')
    await new Promise((r) => setTimeout(r, 50))
    expect(wrapper.find('input[aria-invalid="true"]').exists()).toBe(true)
    expect(wrapper.html()).toContain('text-danger')
  })
})
