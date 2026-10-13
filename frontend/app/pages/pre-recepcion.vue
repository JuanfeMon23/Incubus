<template>
  <div class="grid gap-6 lg:grid-cols-[22rem_1fr]">
    <!-- Ingreso -->
    <form class="space-y-3 rounded-xl border border-zinc-200 bg-white p-4" @submit.prevent="submit">
      <h1 class="text-lg font-semibold">Ingreso de paciente</h1>

      <label class="block text-sm">
        Escanear cédula (código de barras)
        <input
          ref="scanInput"
          v-model="scan"
          autofocus
          placeholder="Enfoque aquí y escanee"
          class="field"
          @keydown.enter.prevent="parseScan"
        >
      </label>
      <p v-if="scanError" class="text-sm text-red-600">{{ scanError }}</p>

      <div class="grid grid-cols-2 gap-2">
        <label class="text-sm">Documento<input v-model="form.document_number" required class="field"></label>
        <label class="text-sm">Sexo
          <select v-model="form.sex" class="field">
            <option value="">—</option>
            <option value="M">M</option>
            <option value="F">F</option>
          </select>
        </label>
        <label class="text-sm">Primer nombre<input v-model="form.first_name" required class="field"></label>
        <label class="text-sm">Segundo nombre<input v-model="form.second_name" class="field"></label>
        <label class="text-sm">Primer apellido<input v-model="form.first_last_name" required class="field"></label>
        <label class="text-sm">Segundo apellido<input v-model="form.second_last_name" class="field"></label>
        <label class="text-sm">Nacimiento<input v-model="form.birth_date" type="date" class="field"></label>
        <label class="text-sm">RH<input v-model="form.blood_type" maxlength="3" class="field"></label>
      </div>

      <fieldset>
        <legend class="text-sm">Prioridad</legend>
        <div class="mt-1 grid grid-cols-2 gap-2">
          <label
            v-for="p in priorities"
            :key="p.id"
            class="flex cursor-pointer items-center gap-2 rounded-lg border p-2 text-sm"
            :class="priorityId === p.id ? 'border-zinc-900' : 'border-zinc-200'"
          >
            <input v-model="priorityId" type="radio" :value="p.id" class="sr-only">
            <span class="h-3 w-3 rounded-full" :style="{ backgroundColor: p.color_hex }" />
            {{ p.name }}
          </label>
        </div>
      </fieldset>

      <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      <button class="w-full rounded-lg bg-zinc-900 py-2 text-sm font-medium text-white disabled:opacity-50" :disabled="!priorityId || busy">
        Ingresar a la cola
      </button>
    </form>

    <!-- Cola -->
    <section>
      <h2 class="mb-3 text-lg font-semibold">En pre-recepción ({{ entries.length }})</h2>
      <p v-if="listError" class="text-sm text-red-600">{{ listError }}</p>
      <ul class="space-y-2">
        <li
          v-for="e in entries"
          :key="e.id"
          class="flex items-center gap-3 rounded-xl border border-zinc-200 bg-white p-3"
          :style="{ borderLeft: `6px solid ${e.priority.color_hex}` }"
        >
          <div class="min-w-0 flex-1">
            <p class="truncate font-medium">{{ fullName(e.patient) }}</p>
            <p class="text-xs text-zinc-500">
              {{ e.patient.document_type }} {{ e.patient.document_number }} · espera {{ waitingLabel(e.arrived_at) }}
            </p>
          </div>
          <PriorityBadge :priority="e.priority" />
          <button class="rounded-lg border border-red-200 px-2 py-1 text-xs text-red-700" @click="removing = e">
            Retirar
          </button>
        </li>
        <li v-if="!entries.length" class="text-sm text-zinc-500">Sin pacientes en espera.</li>
      </ul>
    </section>

    <ReasonDialog
      v-if="removing"
      title="Retirar de la cola"
      confirm-label="Retirar"
      :reasons="removalReasons"
      @cancel="removing = null"
      @confirm="remove"
    />
  </div>
</template>

<script setup lang="ts">
import type { Patient, Priority, Reason } from '../types'

const api = useApi()
const { entries, error: listError, refresh } = useQueueList(['pre_recepcion'])

const priorities = ref<Priority[]>([])
const removalReasons = ref<Reason[]>([])
onMounted(async () => {
  ;[priorities.value, removalReasons.value] = await Promise.all([
    api<Priority[]>('/priorities'),
    api<Reason[]>('/removal-reasons')
  ])
  priorityId.value = priorities.value.find((p) => p.code === 'media')?.id ?? ''
})

const blank = () => ({
  document_number: '',
  first_name: '',
  second_name: '',
  first_last_name: '',
  second_last_name: '',
  sex: '' as '' | 'M' | 'F',
  birth_date: '',
  blood_type: ''
})
const form = reactive(blank())
const priorityId = ref('')
const scan = ref('')
const scanError = ref('')
const error = ref('')
const busy = ref(false)
const removing = ref<{ id: string } | null>(null)

async function parseScan() {
  scanError.value = ''
  try {
    const data = await api<Record<string, string | null>>('/patients/parse-cedula', {
      method: 'POST',
      body: { raw: scan.value }
    })
    Object.assign(form, {
      document_number: data.document_number ?? '',
      first_name: data.first_name ?? '',
      second_name: data.second_name ?? '',
      first_last_name: data.first_last_name ?? '',
      second_last_name: data.second_last_name ?? '',
      sex: data.sex ?? '',
      birth_date: data.birth_date ?? '',
      blood_type: data.blood_type ?? ''
    })
    scan.value = ''
  } catch (e) {
    scanError.value = apiErrorMessage(e)
  }
}

async function submit() {
  busy.value = true
  error.value = ''
  const clean = Object.fromEntries(
    Object.entries(form).map(([k, v]) => [k, v === '' ? null : v])
  ) as Partial<Patient>
  try {
    await api('/queue', { method: 'POST', body: { patient: clean, priority_id: priorityId.value } })
    Object.assign(form, blank())
    await refresh()
  } catch (e) {
    error.value = apiErrorMessage(e)
  } finally {
    busy.value = false
  }
}

async function remove(payload: { reason_id: string; note: string | null }) {
  if (!removing.value) return
  try {
    await api(`/queue/${removing.value.id}/remove`, { method: 'POST', body: payload })
    removing.value = null
    await refresh()
  } catch (e) {
    listError.value = apiErrorMessage(e)
    removing.value = null
  }
}
</script>

<style scoped>
.field { margin-top: 0.25rem; width: 100%; border: 1px solid #d4d4d8; border-radius: 0.5rem; padding: 0.4rem 0.5rem; }
</style>
