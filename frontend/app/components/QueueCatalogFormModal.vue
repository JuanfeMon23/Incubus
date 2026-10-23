<template>
  <UiFormModal
    v-model:open="open"
    :title="title"
    :description="isEdit ? `Código: ${item?.code}. El código no se puede cambiar.` : undefined"
    size="md"
    :submitting="isSubmitting"
    :form-error="formError"
    :submit-label="isEdit ? 'Guardar cambios' : 'Crear'"
    @submit="onSubmit"
  >
    <UiFormField v-if="!isEdit" name="code" label="Código" required hint="Minúsculas, números y guiones; no se podrá cambiar después.">
      <UiTextInput placeholder="p. ej. sin-datos" maxlength="64" />
    </UiFormField>
    <UiFormField name="name" label="Nombre" required>
      <UiTextInput maxlength="100" />
    </UiFormField>

    <template v-if="priority">
      <UiFormField name="color_hex" label="Color" required hint="Formato #RRGGBB.">
        <div class="flex items-center gap-2">
          <input
            type="color"
            class="h-10 w-12 shrink-0 cursor-pointer rounded-md border border-border bg-surface p-1"
            aria-label="Elegir color"
            :value="colorInputValue(values.color_hex)"
            @input="setFieldValue('color_hex', ($event.target as HTMLInputElement).value.toUpperCase())"
          >
          <UiTextInput placeholder="#FF8800" maxlength="7" />
          <PriorityBadge :priority="preview" />
        </div>
      </UiFormField>
      <UiFormField name="rank" label="Orden" required hint="Número entero; menor orden = más urgente. No puede repetirse.">
        <UiTextInput type="number" min="0" step="1" />
      </UiFormField>
    </template>
  </UiFormModal>
</template>

<script setup lang="ts">
import type { QueueAdminItem, QueueAdminKind } from '../types'
import {
  buildCreatePayload,
  buildUpdatePayload,
  catalogFormSchema,
  colorInputValue,
  HEX_PATTERN,
  isPriorityKind,
  KIND_INFO,
  queueAdminErrorMessage
} from '../utils/queueAdmin'

const props = defineProps<{ kind: QueueAdminKind, item: QueueAdminItem | null }>()
const emit = defineEmits<{ saved: [] }>()
const open = defineModel<boolean>('open', { required: true })

const api = useQueueAdminApi(props.kind)
const priority = isPriorityKind(props.kind)
const isEdit = props.item !== null
const info = KIND_INFO[props.kind]
const title = isEdit ? `Editar ${info.noun}` : `${info.feminine ? 'Nueva' : 'Nuevo'} ${info.noun}`

// El schema depende del modo (el code solo se valida al crear): el panel recrea el modal
// con `v-if` en cada apertura, así que se fija al montar.
const schema = catalogFormSchema({ priority, create: !isEdit })
const { submit, isSubmitting, formError, values, setFieldValue } = useZodForm(schema, {
  initialValues: () => ({
    code: props.item?.code ?? '',
    name: props.item?.name ?? '',
    color_hex: props.item?.color_hex ?? '#3B82F6',
    rank: props.item?.rank ?? ''
  }),
  resetOn: open
})

const preview = computed(() => ({
  id: 'preview',
  code: 'preview',
  name: values.name?.trim() || 'Vista previa',
  color_hex: HEX_PATTERN.test(values.color_hex ?? '') ? String(values.color_hex) : '#9CA3AF',
  rank: 0
}))

const onSubmit = submit(async (v) => {
  try {
    if (props.item) {
      const body = buildUpdatePayload(props.kind, v, props.item)
      if (body) await api.update(props.item.id, body)
    } else {
      await api.create(buildCreatePayload(props.kind, v))
    }
  } catch (err) {
    // 409 (nombre/código/orden repetido): mensaje legible con la explicación, no el crudo.
    if ((err as { status?: number }).status === 409) {
      formError.value = queueAdminErrorMessage(err, props.kind)
      return
    }
    throw err
  }
  emit('saved')
  open.value = false
})
</script>
