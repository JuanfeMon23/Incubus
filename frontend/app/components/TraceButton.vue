<template>
  <template v-if="canTrace">
    <UiButton size="sm" variant="ghost" @click.stop="open = true">Ver trazabilidad</UiButton>
    <UiModal v-if="open" :open="true" title="Trazabilidad de la prueba" size="lg" @close="open = false">
      <TraceView :order-number="orderNumber" :test-id="testId" />
      <template #footer="{ close }">
        <UiButton variant="ghost" @click="close">Cerrar</UiButton>
      </template>
    </UiModal>
  </template>
</template>

<script setup lang="ts">
import { TAGS } from '../utils/tags'

/** Botón «Ver trazabilidad» de una prueba: solo con `results.trace`; abre la línea de tiempo en un modal. */
defineProps<{ orderNumber: string; testId: string }>()
const open = ref(false)
const canTrace = useCan(TAGS.results.trace)
</script>
