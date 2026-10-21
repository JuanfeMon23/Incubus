<template>
  <template v-if="canView">
    <UiButton size="sm" variant="ghost" @click.stop="open = true">Historial</UiButton>
    <QueueHistoryModal v-if="open" :entry-id="entryId" @close="open = false" />
  </template>
</template>

<script setup lang="ts">
import { VIEW_TAGS } from '../utils/tags'

/** Botón "Historial" de un turno: solo con el `view` de alguna etapa (lo mismo que exige el backend). */
defineProps<{ entryId: string }>()
const open = ref(false)
const canView = useCan(VIEW_TAGS, 'any')
</script>
