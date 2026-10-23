<template>
  <UiModal :open="true" title="Historial del turno" size="md" @close="emit('close')">
    <div v-if="loading" class="flex justify-center py-6">
      <UiSpinner color="primary" label="Cargando historial" />
    </div>
    <UiAlert v-else-if="error" variant="danger" :message="error" />
    <p v-else-if="!items.length" class="py-6 text-center text-sm text-text-muted">
      Este turno aún no tiene movimientos registrados.
    </p>
    <ol v-else class="space-y-4 border-l-2 border-border pl-4">
      <li v-for="item in items" :key="item.key" class="relative">
        <span class="absolute -left-[1.4rem] top-1.5 h-2.5 w-2.5 rounded-full bg-primary-500" aria-hidden="true" />
        <p class="text-xs text-text-muted">{{ item.when }}</p>
        <p class="font-semibold">{{ item.action }}</p>
        <p v-if="item.transition" class="text-sm">{{ item.transition }}</p>
        <p v-if="item.reason" class="text-sm text-text-muted">Motivo: {{ item.reason }}</p>
        <p v-if="item.note" class="text-sm text-text-muted">{{ item.reason ? 'Nota' : 'Motivo' }}: {{ item.note }}</p>
        <p class="text-sm">Por: <span class="font-medium">{{ item.who }}</span></p>
      </li>
    </ol>
    <template #footer="{ close }">
      <UiButton variant="ghost" @click="close">Cerrar</UiButton>
    </template>
  </UiModal>
</template>

<script setup lang="ts">
import type { QueueHistoryRow } from '../types'
import { historyItems } from '../utils/queueHistory'

/** Quién hizo qué en un turno de la cola (`GET /queue/{id}/history`). */
const props = defineProps<{ entryId: string }>()
const emit = defineEmits<{ close: [] }>()

const api = useLeoAppApi()
const user = useLeoUser()
const rows = ref<QueueHistoryRow[]>([])
const loading = ref(true)
const error = ref('')
const items = computed(() => historyItems(rows.value, user.value?.id))

onMounted(async () => {
  try {
    rows.value = await api.get<QueueHistoryRow[]>(`/queue/${props.entryId}/history`)
  } catch (err) {
    error.value = leoErrorMessage(err)
  } finally {
    loading.value = false
  }
})
</script>
