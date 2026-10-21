<template>
  <article
    class="group relative overflow-hidden rounded-xl border bg-surface shadow-sm transition-all"
    :class="[
      selected ? 'border-primary-500 ring-2 ring-primary-100' : 'border-border',
      selectable ? 'cursor-pointer hover:-translate-y-0.5 hover:shadow-md' : '',
      compact ? 'p-3' : 'p-4'
    ]"
    :tabindex="selectable ? 0 : undefined"
    :role="selectable ? 'button' : undefined"
    @click="selectable && emit('select')"
    @keydown.enter="selectable && emit('select')"
  >
    <!-- franja con el color de la prioridad -->
    <span
      class="absolute inset-y-0 left-0 w-1.5"
      :style="{ backgroundColor: entry.priority.color_hex }"
      aria-hidden="true"
    />

    <div class="flex items-start gap-3 pl-1.5">
      <span
        class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white"
        :style="{ backgroundColor: entry.priority.color_hex }"
        aria-hidden="true"
      >{{ initials }}</span>

      <div class="min-w-0 flex-1">
        <div class="flex items-start justify-between gap-2">
          <p class="truncate font-semibold leading-tight">{{ fullName(entry.patient) }}</p>
          <PriorityBadge :priority="entry.priority" class="shrink-0" />
        </div>
        <p class="mt-0.5 truncate text-xs text-text-muted">
          {{ entry.patient.document_type }} {{ entry.patient.document_number }}
          <template v-if="age !== null"> · {{ age }} años</template>
          <template v-if="entry.patient.sex"> · {{ entry.patient.sex === 'F' ? 'Mujer' : 'Hombre' }}</template>
        </p>

        <div class="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
          <span class="inline-flex items-center gap-1 rounded-full bg-default-100 px-2 py-0.5 text-default-700">
            <svg viewBox="0 0 24 24" class="h-3 w-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
            </svg>
            {{ waitingLabel(entry.arrived_at) }}
          </span>
          <span
            v-if="entry.order_number"
            class="rounded-full bg-primary-50 px-2 py-0.5 font-mono font-semibold text-primary-700"
          >#{{ entry.order_number }}</span>
          <span
            v-if="entry.assigned_professional_name"
            class="inline-flex items-center gap-1 rounded-full bg-secondary-50 px-2 py-0.5 text-secondary-700"
          >
            <svg viewBox="0 0 24 24" class="h-3 w-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" />
            </svg>
            {{ entry.assigned_professional_name }}
          </span>
          <span
            v-if="entry.claimed_by && showClaimedBy"
            class="rounded-full bg-success-50 px-2 py-0.5 text-success-700"
          >{{ claimedLabel }} {{ entry.claimed_by }}</span>
          <slot name="chips" />
        </div>

        <div v-if="$slots.default" class="mt-3"><slot /></div>
      </div>
    </div>

    <div class="mt-3 flex justify-end gap-2 pl-1.5" @click.stop>
      <QueueHistoryButton :entry-id="entry.id" />
      <slot name="actions" />
    </div>
  </article>
</template>

<script setup lang="ts">
import type { QueueEntry } from '../types'

const props = withDefaults(
  defineProps<{
    entry: QueueEntry
    selected?: boolean
    selectable?: boolean
    compact?: boolean
    showClaimedBy?: boolean
  }>(),
  { selected: false, selectable: false, compact: false, showClaimedBy: false }
)
const emit = defineEmits<{ select: [] }>()

const initials = computed(() => {
  const p = props.entry.patient
  return `${p.first_name?.[0] ?? ''}${p.first_last_name?.[0] ?? ''}`.toUpperCase()
})
/** Etiqueta de quien tomó el turno (toma de muestras: "Tomado por"). */
const claimedLabel = computed(() => (props.entry.status === 'en_atencion_toma_muestras' ? 'Tomado por' : 'Atiende:'))
const age = computed(() => ageFrom(props.entry.patient.birth_date))
</script>
