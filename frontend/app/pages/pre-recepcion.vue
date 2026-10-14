<template>
  <div class="grid gap-6 lg:grid-cols-[24rem_1fr]">
    <UiCard title="Ingreso de paciente" description="Escanee la cédula o digite los datos.">
      <form class="space-y-3" @submit.prevent="submit">
        <UiFormField label="Escanear cédula (código de barras)" :error="scanError">
          <UiTextInput
            v-model="scan"
            autofocus
            placeholder="Enfoque aquí y escanee"
            @keydown.enter.prevent="parseScan"
          />
        </UiFormField>

        <div class="grid grid-cols-2 gap-3">
          <UiFormField label="Documento" required><UiTextInput v-model="form.document_number" required /></UiFormField>
          <UiFormField label="Sexo">
            <UiSelect v-model="form.sex" :options="sexOptions" empty-label="—" />
          </UiFormField>
          <UiFormField label="Primer nombre" required><UiTextInput v-model="form.first_name" required /></UiFormField>
          <UiFormField label="Segundo nombre"><UiTextInput v-model="form.second_name" /></UiFormField>
          <UiFormField label="Primer apellido" required><UiTextInput v-model="form.first_last_name" required /></UiFormField>
          <UiFormField label="Segundo apellido"><UiTextInput v-model="form.second_last_name" /></UiFormField>
          <UiFormField label="Nacimiento"><UiTextInput v-model="form.birth_date" type="date" /></UiFormField>
          <UiFormField label="RH"><UiTextInput v-model="form.blood_type" /></UiFormField>
        </div>

        <fieldset>
          <legend class="mb-1 text-sm font-medium">Prioridad</legend>
          <div class="grid grid-cols-2 gap-2">
            <label
              v-for="p in priorities"
              :key="p.id"
              class="flex cursor-pointer items-center gap-2 rounded-md border-2 p-2 text-sm transition-colors"
              :class="priorityId === p.id ? 'border-primary-500 bg-primary-50' : 'border-border'"
            >
              <input v-model="priorityId" type="radio" :value="p.id" class="sr-only">
              <span class="h-3 w-3 rounded-full" :style="{ backgroundColor: p.color_hex }" />
              {{ p.name }}
            </label>
          </div>
        </fieldset>

        <UiAlert v-if="error" variant="danger" :message="error" />
        <UiButton type="submit" class="w-full" :disabled="!priorityId" :loading="busy">
          Ingresar a la cola
        </UiButton>
      </form>
    </UiCard>

    <section>
      <h2 class="mb-3 text-lg font-semibold">En pre-recepción ({{ entries.length }})</h2>
      <UiAlert v-if="listError" variant="danger" :message="listError" class="mb-3" />
      <ul class="space-y-2">
        <li v-for="e in entries" :key="e.id">
          <UiCard padding="sm" :style="{ borderLeft: `6px solid ${e.priority.color_hex}` }">
            <div class="flex items-center gap-3">
              <div class="min-w-0 flex-1">
                <p class="truncate font-medium">{{ fullName(e.patient) }}</p>
                <p class="text-xs text-text-muted">
                  {{ e.patient.document_type }} {{ e.patient.document_number }} · espera {{ waitingLabel(e.arrived_at) }}
                </p>
              </div>
              <PriorityBadge :priority="e.priority" />
              <UiButton size="sm" variant="danger-ghost" @click="removing = e">Retirar</UiButton>
            </div>
          </UiCard>
        </li>
        <li v-if="!entries.length" class="text-sm text-text-muted">Sin pacientes en espera.</li>
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

const sexOptions = [{ value: 'M', label: 'M' }, { value: 'F', label: 'F' }]
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
