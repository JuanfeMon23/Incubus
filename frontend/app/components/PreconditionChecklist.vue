<template>
  <UiAlert variant="warning" :title="title">
    <ul class="space-y-3 text-sm">
      <li v-for="p in items" :key="p.key" class="space-y-1">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <strong>{{ p.name }}</strong>
            <span v-if="formatDuration(p.duration_value, p.duration_unit)">
              — {{ formatDuration(p.duration_value, p.duration_unit) }}
            </span>
            <span v-if="p.patient_instructions">: {{ p.patient_instructions }}</span>
          </div>
          <div class="flex gap-1">
            <UiButton
              size="sm"
              :variant="modelValue[p.key]?.met === true ? 'primary' : 'secondary'"
              @click="set(p.key, true)"
            >Cumple</UiButton>
            <UiButton
              size="sm"
              :variant="modelValue[p.key]?.met === false ? 'danger' : 'secondary'"
              @click="set(p.key, false)"
            >No cumple</UiButton>
          </div>
        </div>
        <p v-if="previous && previous[p.key] !== undefined && previous[p.key] !== null" class="text-xs text-text-muted">
          Recepción: {{ previous[p.key] ? 'cumple' : 'no cumple' }}
        </p>
        <UiTextInput
          v-if="modelValue[p.key]?.met === false"
          :model-value="modelValue[p.key]?.note ?? ''"
          placeholder="Nota obligatoria: por qué no cumple"
          @update:model-value="setNote(p.key, String($event ?? ''))"
        />
      </li>
    </ul>
  </UiAlert>
</template>

<script setup lang="ts">
import type { CheckMap } from '../utils/checks'

export interface ChecklistItem {
  key: string
  name: string
  duration_value: number | null
  duration_unit: string | null
  patient_instructions: string | null
}

const props = defineProps<{
  title: string
  items: ChecklistItem[]
  modelValue: CheckMap
  /** Resultado de la verificación anterior (recepción), por llave. */
  previous?: Record<string, boolean | null>
}>()
const emit = defineEmits<{ 'update:modelValue': [value: CheckMap] }>()

function set(key: string, met: boolean) {
  emit('update:modelValue', {
    ...props.modelValue,
    [key]: { met, note: met ? '' : (props.modelValue[key]?.note ?? '') }
  })
}

function setNote(key: string, note: string) {
  emit('update:modelValue', { ...props.modelValue, [key]: { met: false, note } })
}
</script>
