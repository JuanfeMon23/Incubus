<template>
  <div v-if="range && hasBounds" class="select-none" :aria-label="ariaLabel" role="img">
    <div class="relative h-2.5 overflow-hidden rounded-full bg-default-200">
      <!-- zona normal -->
      <div
        class="absolute inset-y-0 bg-success-300"
        :style="{ left: `${normalFrom}%`, width: `${normalTo - normalFrom}%` }"
      />
      <!-- zonas críticas -->
      <div
        v-if="criticalLowPos !== null"
        class="absolute inset-y-0 left-0 bg-danger-300"
        :style="{ width: `${criticalLowPos}%` }"
      />
      <div
        v-if="criticalHighPos !== null"
        class="absolute inset-y-0 right-0 bg-danger-300"
        :style="{ width: `${100 - criticalHighPos}%` }"
      />
    </div>
    <div class="relative mt-0.5 h-3">
      <span
        v-if="markerPos !== null"
        class="absolute -top-[0.95rem] h-3.5 w-1 -translate-x-1/2 rounded-full ring-2 ring-white"
        :class="markerClass"
        :style="{ left: `${markerPos}%` }"
      />
    </div>
    <div class="flex justify-between text-[0.65rem] text-text-muted">
      <span>{{ range.low ?? '' }}</span>
      <span>{{ range.high ?? '' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Range {
  low: number | null
  high: number | null
  critical_low: number | null
  critical_high: number | null
}

const props = defineProps<{
  range: Range | null
  value: number | null
  flag: string | null
}>()

const hasBounds = computed(() => props.range && (props.range.low !== null || props.range.high !== null))

// Escala visible: del mínimo al máximo con margen, incluyendo el valor.
const bounds = computed(() => {
  const r = props.range
  if (!r) return { min: 0, max: 1 }
  const points = [r.critical_low, r.low, r.high, r.critical_high, props.value].filter(
    (n): n is number => typeof n === 'number'
  )
  const lo = Math.min(...points)
  const hi = Math.max(...points)
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.25
  return { min: lo - pad, max: hi + pad }
})

function pos(n: number | null): number | null {
  if (n === null || n === undefined) return null
  const { min, max } = bounds.value
  return Math.min(100, Math.max(0, ((n - min) / (max - min)) * 100))
}

const normalFrom = computed(() => pos(props.range?.low ?? null) ?? 0)
const normalTo = computed(() => pos(props.range?.high ?? null) ?? 100)
const criticalLowPos = computed(() => pos(props.range?.critical_low ?? null))
const criticalHighPos = computed(() => pos(props.range?.critical_high ?? null))
const markerPos = computed(() => (props.value === null ? null : pos(props.value)))

const markerClass = computed(() => {
  if (props.flag === 'normal') return 'bg-success-600'
  if (props.flag?.startsWith('critical')) return 'bg-danger-600'
  return 'bg-warning-600'
})

const ariaLabel = computed(() => {
  const r = props.range
  return r ? `Rango normal ${r.low ?? ''} a ${r.high ?? ''}` : 'Sin rango de referencia'
})
</script>
