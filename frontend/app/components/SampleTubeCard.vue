<template>
  <article
    class="flex gap-4 rounded-xl border-2 bg-surface p-3 transition-colors"
    :class="sample.collected_at ? 'border-success-300 bg-success-50' : 'border-border'"
  >
    <div class="flex w-12 shrink-0 flex-col items-center justify-center">
      <TubeIcon
        :color="sample.cap_color_hex"
        :collected="!!sample.collected_at"
        :fill="fillRatio"
        :size="30"
        :label="`Tubo ${sample.name}`"
      />
    </div>

    <div class="min-w-0 flex-1 space-y-2">
      <header class="flex flex-wrap items-center gap-2">
        <h3 class="font-semibold leading-tight">{{ sample.name }}</h3>
        <span
          v-if="sample.draw_order !== null"
          class="rounded-full bg-default-100 px-2 py-0.5 text-xs font-medium text-default-700"
        >Extracción #{{ sample.draw_order }}</span>
        <span
          v-if="formatVolume(sample.required_volume_ml)"
          class="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-700"
        >{{ formatVolume(sample.required_volume_ml) }}</span>
      </header>

      <ul class="flex flex-wrap gap-1">
        <li
          v-for="code in sample.test_codes"
          :key="code"
          class="rounded-md bg-default-100 px-1.5 py-0.5 font-mono text-[0.7rem] text-default-700"
        >{{ code }}</li>
      </ul>

      <p class="flex flex-wrap items-center gap-1 text-xs text-text-muted">
        <span class="font-medium">Ruta:</span>
        <template v-if="sample.area_route.length">
          <template v-for="(area, i) in sample.area_route" :key="area">
            <span class="rounded bg-secondary-50 px-1.5 py-0.5 font-semibold text-secondary-700">{{ area }}</span>
            <span v-if="i < sample.area_route.length - 1" aria-hidden="true">›</span>
          </template>
        </template>
        <span v-else>—</span>
      </p>

      <p v-if="sample.collection_instructions" class="rounded-md bg-warning-50 px-2 py-1 text-xs text-warning-800">
        {{ sample.collection_instructions }}
      </p>

      <slot />
    </div>

    <div v-if="$slots.actions" class="flex shrink-0 items-center">
      <slot name="actions" />
    </div>
  </article>
</template>

<script setup lang="ts">
import type { OrderSample } from '../types'
import { formatVolume } from '../utils/sampling'

const props = defineProps<{ sample: OrderSample }>()

// Relleno visual: proporcional al volumen requerido (tope 10 mL).
const fillRatio = computed(() => {
  const ml = props.sample.required_volume_ml
  return ml ? Math.min(ml / 10, 1) * 0.7 + 0.3 : 0.6
})
</script>
