<template>
  <UiFormModal
    v-model:open="open"
    title="Hacer predeterminada"
    :description="`«${item.name}» será la prioridad que se preselecciona al ingresar pacientes a la cola.`"
    size="sm"
    :submitting="isSubmitting"
    :form-error="formError"
    submit-label="Hacer predeterminada"
    @submit="onSubmit"
  >
    <UiFormField name="reason" label="Motivo" hint="Opcional. Queda en el historial.">
      <UiTextarea :rows="3" maxlength="255" />
    </UiFormField>
  </UiFormModal>
</template>

<script setup lang="ts">
import type { QueueAdminItem, QueueAdminKind } from '../types'
import { queueAdminErrorMessage, setDefaultSchema } from '../utils/queueAdmin'

const props = defineProps<{ kind: QueueAdminKind, item: QueueAdminItem }>()
const emit = defineEmits<{ saved: [] }>()
const open = defineModel<boolean>('open', { required: true })

const api = useQueueAdminApi(props.kind)
const toast = useToast()
const { submit, isSubmitting, formError } = useZodForm(setDefaultSchema, { initialValues: { reason: '' }, resetOn: open })

const onSubmit = submit(async ({ reason }) => {
  try {
    await api.setDefault(props.item.id, reason || undefined)
  } catch (err) {
    // 409 (inactiva o ya es la predeterminada) y 404: legible, dentro del modal.
    formError.value = queueAdminErrorMessage(err, props.kind)
    return
  }
  toast.success(`«${props.item.name}» es ahora la prioridad predeterminada.`)
  emit('saved')
  open.value = false
})
</script>
