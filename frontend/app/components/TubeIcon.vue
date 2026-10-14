<template>
  <svg
    :width="size"
    :height="size * 2.6"
    viewBox="0 0 24 62"
    role="img"
    :aria-label="label"
    class="shrink-0"
  >
    <!-- cuerpo del tubo -->
    <path
      d="M5 12h14v36a7 7 0 0 1-14 0V12Z"
      fill="#f4f4f5"
      stroke="#a1a1aa"
      stroke-width="1.5"
      stroke-linejoin="round"
    />
    <!-- muestra -->
    <path
      :d="`M6 ${liquidTop}h12v${48 - liquidTop}a6 6 0 0 1-12 0Z`"
      :fill="liquid"
      opacity="0.85"
    />
    <!-- brillo -->
    <path d="M8 16v28" stroke="#fff" stroke-width="1.5" stroke-linecap="round" opacity="0.8" />
    <!-- tapa -->
    <rect x="3" y="3" width="18" height="10" rx="2.5" :fill="capColor" stroke="rgb(0 0 0 / 0.25)" stroke-width="1" />
    <rect x="3" y="3" width="18" height="3" rx="1.5" fill="#fff" opacity="0.25" />
    <!-- marca de tomado -->
    <g v-if="collected">
      <circle cx="12" cy="35" r="7" fill="#17c964" />
      <path d="m8.8 35 2.2 2.3 4.2-4.6" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </g>
  </svg>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    /** Color de la tapa (hex); gris si el tipo de muestra no lo define. */
    color?: string | null
    /** Relleno del tubo (0 a 1) para sugerir el volumen. */
    fill?: number
    collected?: boolean
    size?: number
    label?: string
  }>(),
  { color: null, fill: 0.6, collected: false, size: 28, label: 'Tubo de muestra' }
)

const capColor = computed(() => props.color || '#a1a1aa')
// La muestra toma un tono suave del color de la tapa.
const liquid = computed(() => props.color || '#d4d4d8')
const liquidTop = computed(() => 48 - Math.round(36 * Math.min(Math.max(props.fill, 0.1), 1)))
</script>
