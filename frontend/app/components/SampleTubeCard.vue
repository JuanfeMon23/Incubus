<template>
  <article
    class="relative overflow-hidden rounded-2xl border-2 bg-surface transition-all"
    :class="cardClass"
  >
    <!-- Banda de estado en el modo toma -->
    <div
      v-if="variant === 'collect'"
      class="flex items-center justify-between px-4 py-1.5 text-xs font-semibold"
      :class="sample.collected_at ? 'bg-success-500 text-white' : 'bg-default-100 text-default-600'"
    >
      <span>
        <template v-if="index !== undefined">Tubo {{ index + 1 }}{{ total ? ` de ${total}` : '' }}</template>
        <template v-else>Tubo</template>
      </span>
      <span v-if="sample.collected_at">
        ✓ Tomado {{ formatDateTime(sample.collected_at) }}<template v-if="sample.collected_by"> · {{ sample.collected_by }}</template>
      </span>
      <span v-else>Pendiente</span>
    </div>

    <div class="flex gap-4 p-4">
      <!-- Tubo -->
      <div
        class="flex w-16 shrink-0 flex-col items-center justify-center rounded-xl py-2"
        :style="{ backgroundColor: tint }"
      >
        <TubeIcon
          :color="sample.cap_color_hex"
          :collected="!!sample.collected_at"
          :fill="fillRatio"
          :size="variant === 'collect' ? 38 : 32"
          :label="`Tubo ${sample.name}`"
        />
        <span
          v-if="sample.draw_order !== null"
          class="mt-1 rounded-full bg-white/80 px-1.5 text-[0.65rem] font-bold text-default-700"
          :title="`Orden de extracción ${sample.draw_order}`"
        >#{{ sample.draw_order }}</span>
      </div>

      <div class="min-w-0 flex-1 space-y-3">
        <header>
          <h3 class="font-semibold leading-tight">{{ sample.name }}</h3>
          <div class="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
            <span
              v-if="formatVolume(sample.required_volume_ml)"
              class="inline-flex items-center gap-1 rounded-full bg-primary-50 px-2 py-0.5 font-medium text-primary-700"
            >
              <svg viewBox="0 0 24 24" class="h-3 w-3" fill="currentColor" aria-hidden="true">
                <path d="M12 2.5s6 6.2 6 10.5a6 6 0 0 1-12 0C6 8.7 12 2.5 12 2.5Z" />
              </svg>
              {{ formatVolume(sample.required_volume_ml) }}
            </span>
            <span
              v-if="variant === 'print' && sample.labels_printed_at"
              class="rounded-full bg-success-50 px-2 py-0.5 font-medium text-success-700"
            >Etiqueta impresa</span>
          </div>
        </header>

        <!-- Exámenes y ruta -->
        <div class="grid gap-2 text-xs sm:grid-cols-2">
          <div>
            <p class="mb-1 font-medium text-text-muted">Exámenes</p>
            <ul class="flex flex-wrap gap-1">
              <li
                v-for="code in sample.test_codes"
                :key="code"
                class="rounded-md bg-default-100 px-1.5 py-0.5 font-mono text-[0.7rem] font-semibold text-default-700"
              >{{ code }}</li>
            </ul>
          </div>
          <div>
            <p class="mb-1 font-medium text-text-muted">Ruta</p>
            <div v-if="sample.area_route.length" class="flex flex-wrap items-center gap-1">
              <template v-for="(area, i) in sample.area_route" :key="area">
                <span class="rounded-md bg-secondary-50 px-1.5 py-0.5 font-bold text-secondary-700">{{ area }}</span>
                <span v-if="i < sample.area_route.length - 1" class="text-text-muted" aria-hidden="true">→</span>
              </template>
            </div>
            <span v-else class="text-text-muted">—</span>
          </div>
        </div>

        <div
          v-if="sample.collection_instructions"
          class="flex items-start gap-2 rounded-lg bg-warning-50 px-3 py-2 text-xs text-warning-800"
        >
          <svg viewBox="0 0 24 24" class="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
          </svg>
          <span>{{ sample.collection_instructions }}</span>
        </div>

        <slot />
      </div>
    </div>

    <!-- Acción principal (toma): botón grande -->
    <div v-if="$slots.actions" class="border-t border-border bg-default-50 px-4 py-3">
      <slot name="actions" />
    </div>
  </article>
</template>

<script setup lang="ts">
import type { OrderSample } from '../types'
import { formatVolume } from '../utils/sampling'

const props = withDefaults(
  defineProps<{
    sample: OrderSample
    /** `collect`: toma de muestras (estado y acción grande); `print`: impresión. */
    variant?: 'collect' | 'print'
    index?: number
    total?: number
  }>(),
  { variant: 'print', index: undefined, total: undefined }
)

const cardClass = computed(() => {
  if (props.variant === 'collect') {
    return props.sample.collected_at
      ? 'border-success-400 shadow-sm'
      : 'border-border shadow-sm hover:shadow-md'
  }
  return 'border-border shadow-sm'
})

// Fondo suave con el color de la tapa.
const tint = computed(() => {
  const hex = props.sample.cap_color_hex
  return hex && /^#[0-9a-f]{6}$/i.test(hex) ? `${hex}1f` : '#f4f4f5'
})

// Relleno visual: proporcional al volumen requerido (tope 10 mL).
const fillRatio = computed(() => {
  const ml = props.sample.required_volume_ml
  return ml ? Math.min(ml / 10, 1) * 0.7 + 0.3 : 0.6
})
</script>
