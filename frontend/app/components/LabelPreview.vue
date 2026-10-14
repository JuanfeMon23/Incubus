<template>
  <div
    class="w-full max-w-[17.5rem] rounded-md border border-border-strong bg-white p-3 shadow-sm"
    role="img"
    :aria-label="`Etiqueta de ${tubeName} para la orden ${orderNumber}`"
  >
    <p class="truncate text-[0.8rem] font-bold leading-tight">{{ patientName }}</p>
    <p class="truncate text-[0.65rem] text-text-muted">{{ document }} · Orden {{ orderNumber }}</p>
    <img
      :src="`${apiBase}/orders/barcode/${orderNumber}.svg`"
      :alt="`Código de barras ${orderNumber}`"
      class="mt-1 h-9 w-full object-contain object-left"
      loading="lazy"
    >
    <div class="mt-1 flex items-end justify-between gap-2">
      <p class="truncate text-xs font-bold tracking-wide">{{ route || '—' }}</p>
      <p class="max-w-[45%] truncate text-[0.6rem] text-text-muted">{{ tubeName }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  patientName: string
  document: string
  orderNumber: string
  tubeName: string
  areaRoute: string[]
}>()

const apiBase = useRuntimeConfig().public.apiBase
const route = computed(() => props.areaRoute.join(' > '))
</script>
