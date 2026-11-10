<template>
  <div class="space-y-4">
    <UiAlert v-if="error" variant="danger" :message="error" />

    <div v-if="loading && !events.length" class="flex justify-center py-8">
      <UiSpinner color="primary" label="Cargando trazabilidad" />
    </div>
    <p
      v-else-if="!error && !events.length"
      class="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-text-muted"
    >
      {{ emptyMessage }}
    </p>

    <section v-for="day in days" :key="day.key" :aria-label="day.label" class="space-y-3">
      <h3 class="text-sm font-semibold capitalize text-text-muted">{{ day.label }}</h3>
      <ol class="relative space-y-4 border-l-2 border-default-200 pl-6">
        <li v-for="(event, i) in day.events" :key="`${event.at}-${event.step}-${i}`" class="relative" data-testid="trace-event">
          <span
            class="absolute -left-[2.15rem] top-0 flex h-6 w-6 items-center justify-center rounded-full text-white ring-4 ring-surface"
            :class="info(event).dot"
            aria-hidden="true"
          >
            <svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path :d="info(event).icon" />
            </svg>
          </span>
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <time :datetime="event.at" class="font-mono text-xs text-text-muted">{{ timeLabel(event.at) }}</time>
            <span class="text-xs font-semibold uppercase tracking-wide text-text-muted">{{ info(event).label }}</span>
            <span class="rounded-full bg-default-100 px-2 py-0.5 text-xs">{{ SCOPE_LABELS[event.scope] ?? event.scope }}</span>
            <span
              v-if="event.source === 'derived'"
              class="cursor-help rounded-full bg-warning-50 px-2 py-0.5 text-xs font-medium text-warning-700"
              title="Datos anteriores a la trazabilidad detallada"
            >Reconstruido</span>
          </div>
          <p class="font-semibold">{{ event.summary || stepLabel(event.step, traceSteps.items.value) }}</p>
          <p class="text-sm">Por: <span class="font-medium">{{ actorName(event.actor) }}</span></p>
          <details v-if="lines(event).length" class="mt-1 text-sm">
            <summary class="cursor-pointer text-primary-600 hover:underline focus-visible:outline focus-visible:outline-2">Ver detalles</summary>
            <ul class="mt-1 list-disc space-y-0.5 pl-5 text-text-muted">
              <li v-for="(line, j) in lines(event)" :key="j">{{ line }}</li>
            </ul>
          </details>
        </li>
      </ol>
    </section>

    <UiButton v-if="hasMore" variant="secondary" size="sm" :loading="loading" @click="emit('loadMore')">Cargar más</UiButton>
  </div>
</template>

<script setup lang="ts">
import type { TraceEvent, TraceStepCatalogItem } from '../types'
import { actorName, CATEGORY_INFO, detailLines, groupByDay, SCOPE_LABELS, stepCategory, stepLabel, timeLabel } from '../utils/trace'

/** Línea de tiempo de la trazabilidad de una prueba, agrupada por día (presentacional). */
const props = withDefaults(
  defineProps<{
    events: TraceEvent[]
    loading?: boolean
    error?: string
    hasMore?: boolean
    emptyMessage?: string
  }>(),
  { loading: false, error: '', hasMore: false, emptyMessage: 'Sin eventos para mostrar.' }
)
const emit = defineEmits<{ loadMore: [] }>()

// Nombre y categoría de cada paso vienen del catálogo `trace-steps`; íconos y colores son UI (`CATEGORY_INFO`).
const traceSteps = useCatalog<TraceStepCatalogItem>('trace-steps', { includeInactive: true })
const days = computed(() => groupByDay(props.events))
const info = (event: TraceEvent) => CATEGORY_INFO[stepCategory(event.step, traceSteps.items.value)]
const lines = (event: TraceEvent) => detailLines(event)
</script>
