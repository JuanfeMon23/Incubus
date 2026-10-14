<template>
  <UiModal :open="true" :title="title" size="sm" @close="emit('cancel')">
    <form id="reason-form" class="space-y-4" @submit.prevent="submit">
      <UiFormField label="Motivo" required>
        <UiSelect v-model="reasonId" :options="options" placeholder="Seleccione…" required />
      </UiFormField>
      <UiFormField label="Nota (opcional)">
        <UiTextarea v-model="note" :rows="2" />
      </UiFormField>
    </form>
    <template #footer="{ close }">
      <UiButton variant="ghost" @click="close">Cancelar</UiButton>
      <UiButton type="submit" form="reason-form" variant="danger" :disabled="!reasonId">
        {{ confirmLabel }}
      </UiButton>
    </template>
  </UiModal>
</template>

<script setup lang="ts">
import type { Reason } from '../types'

const props = defineProps<{ title: string; confirmLabel: string; reasons: Reason[] }>()
const emit = defineEmits<{
  cancel: []
  confirm: [payload: { reason_id: string; note: string | null }]
}>()
const reasonId = ref('')
const note = ref('')
const options = computed(() => props.reasons.map((r) => ({ value: r.id, label: r.name })))

function submit() {
  if (!reasonId.value) return
  emit('confirm', { reason_id: reasonId.value, note: note.value.trim() || null })
}
</script>
