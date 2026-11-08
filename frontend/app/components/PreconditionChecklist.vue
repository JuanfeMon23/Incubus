<template>
  <UiAlert variant="warning" :title="title">
    <ul class="space-y-3 text-sm">
      <li v-for="item in items" :key="item.key" class="space-y-1">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <strong>{{ item.name }}</strong>
            <span v-if="formatDuration(item.duration_value, item.duration_unit)">
              — {{ formatDuration(item.duration_value, item.duration_unit) }}
            </span>
            <span v-if="item.patient_instructions">: {{ item.patient_instructions }}</span>
          </div>
          <div class="flex gap-1">
            <UiButton
              size="sm"
              :variant="modelValue[item.key]?.met === true ? 'primary' : 'secondary'"
              :disabled="disabled"
              :title="disabled ? disabledHint : undefined"
              @click="set(item.key, true)"
            >Cumple</UiButton>
            <UiButton
              size="sm"
              :variant="modelValue[item.key]?.met === false ? 'danger' : 'secondary'"
              :disabled="disabled"
              :title="disabled ? disabledHint : undefined"
              @click="set(item.key, false)"
            >No cumple</UiButton>
          </div>
        </div>
        <p v-if="previous && previous[item.key] !== undefined && previous[item.key] !== null" class="text-xs text-text-muted">
          Recepción: {{ previous[item.key] ? 'cumple' : 'no cumple' }}
        </p>
        <UiTextInput
          v-if="modelValue[item.key]?.met === false"
          :disabled="disabled"
          :model-value="modelValue[item.key]?.note ?? ''"
          placeholder="Nota obligatoria: por qué no cumple"
          @update:model-value="setNote(item.key, String($event ?? ''))"
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
  /** Solo lectura (p. ej. turno de otra persona). */
  disabled?: boolean
  /** Aviso (`title`) de los controles cuando están deshabilitados. */
  disabledHint?: string
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
