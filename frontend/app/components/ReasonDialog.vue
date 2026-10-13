<template>
  <div class="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
    <form class="w-full max-w-md space-y-4 rounded-xl bg-white p-5 shadow-xl" @submit.prevent="submit">
      <h2 class="text-lg font-semibold">{{ title }}</h2>
      <label class="block text-sm">
        Motivo
        <select v-model="reasonId" required class="mt-1 w-full rounded-lg border border-zinc-300 p-2">
          <option disabled value="">Seleccione…</option>
          <option v-for="r in reasons" :key="r.id" :value="r.id">{{ r.name }}</option>
        </select>
      </label>
      <label class="block text-sm">
        Nota (opcional)
        <textarea v-model="note" rows="2" class="mt-1 w-full rounded-lg border border-zinc-300 p-2" />
      </label>
      <div class="flex justify-end gap-2">
        <button type="button" class="rounded-lg px-3 py-2 text-sm" @click="emit('cancel')">Cancelar</button>
        <button class="rounded-lg bg-red-600 px-3 py-2 text-sm text-white disabled:opacity-50" :disabled="!reasonId">
          {{ confirmLabel }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import type { Reason } from '../types'

defineProps<{ title: string; confirmLabel: string; reasons: Reason[] }>()
const emit = defineEmits<{
  cancel: []
  confirm: [payload: { reason_id: string; note: string | null }]
}>()
const reasonId = ref('')
const note = ref('')

function submit() {
  emit('confirm', { reason_id: reasonId.value, note: note.value.trim() || null })
}
</script>
