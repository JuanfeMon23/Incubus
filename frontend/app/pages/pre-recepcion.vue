<template>
  <div class="grid gap-6 lg:grid-cols-[24rem_1fr]">
    <UiCard title="Ingreso de paciente" description="Escanee la cédula o digite los datos.">
      <form class="space-y-3" novalidate @submit.prevent="onSubmit">
        <UiFormField label="Escanear cédula (código de barras)" :error="scanError">
          <UiTextInput
            v-model="scan"
            autofocus
            placeholder="Enfoque aquí y escanee"
            @keydown.enter.prevent="parseScan"
          />
        </UiFormField>

        <div class="grid grid-cols-2 gap-3">
          <UiFormField name="document_number" label="Documento" required><UiTextInput /></UiFormField>
          <UiFormField name="sex" label="Sexo">
            <UiSelect :options="sexOptions" empty-label="—" />
          </UiFormField>
          <UiFormField name="first_name" label="Primer nombre" required><UiTextInput /></UiFormField>
          <UiFormField name="second_name" label="Segundo nombre"><UiTextInput /></UiFormField>
          <UiFormField name="first_last_name" label="Primer apellido" required><UiTextInput /></UiFormField>
          <UiFormField name="second_last_name" label="Segundo apellido"><UiTextInput /></UiFormField>
          <UiFormField name="birth_date" label="Nacimiento"><UiTextInput type="date" /></UiFormField>
          <UiFormField name="blood_type" label="RH"><UiTextInput /></UiFormField>
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
          <p v-if="errors.priority_id" class="mt-1 text-xs text-danger-600">{{ errors.priority_id }}</p>
        </fieldset>

        <UiAlert v-if="formError" variant="danger" :message="formError" />
        <UiButton type="submit" class="w-full" :loading="isSubmitting">
          Ingresar a la cola
        </UiButton>
      </form>
    </UiCard>

    <section>
      <h2 class="mb-3 text-lg font-semibold">En pre-recepción ({{ entries.length }})</h2>
      <UiAlert v-if="listError" variant="danger" :message="listError" class="mb-3" />
      <div v-if="listLoading" class="flex justify-center py-6"><UiSpinner size="lg" color="primary" label="Cargando cola" /></div>
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
        <li v-if="!entries.length && !listLoading" class="text-sm text-text-muted">Sin pacientes en espera.</li>
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
import type { Priority, Reason } from '../types'
import { intakePatientSchema } from '../utils/patientSchemas'

const sexOptions = [{ value: 'M', label: 'M' }, { value: 'F', label: 'F' }]
const api = useApi()
const toast = useToast()
const { entries, error: listError, loading: listLoading, refresh } = useQueueList(['pre_recepcion'])

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
  blood_type: '',
  priority_id: ''
})
// Errores en rojo bajo cada campo (zod + vee-validate), igual que en Vladimir.
const form = useZodForm(intakePatientSchema, { initialValues: blank })
const { errors, isSubmitting, formError } = form
const priorityId = ref('')
watch(priorityId, (id) => form.setFieldValue('priority_id', id))
const scan = ref('')
const scanError = ref('')
const removing = ref<{ id: string } | null>(null)

async function parseScan() {
  scanError.value = ''
  try {
    const data = await api<Record<string, string | null>>('/patients/parse-cedula', {
      method: 'POST',
      body: { raw: scan.value }
    })
    form.setValues({
      document_number: data.document_number ?? '',
      first_name: data.first_name ?? '',
      second_name: data.second_name ?? '',
      first_last_name: data.first_last_name ?? '',
      second_last_name: data.second_last_name ?? '',
      sex: (data.sex ?? '') as '' | 'M' | 'F',
      birth_date: data.birth_date ?? '',
      blood_type: data.blood_type ?? ''
    })
    scan.value = ''
  } catch (e) {
    scanError.value = apiErrorMessage(e)
    toast.error(scanError.value)
  }
}

const onSubmit = form.submit(async (values) => {
  const { priority_id: priorityValue, ...patient } = values
  try {
    await api('/queue', { method: 'POST', body: { patient, priority_id: priorityValue } })
  } catch (e) {
    toast.error(apiErrorMessage(e))
    throw e
  }
  form.reset()
  priorityId.value = priorities.value.find((p) => p.code === 'media')?.id ?? ''
  toast.success('Paciente ingresado a la cola.')
  await refresh()
})

async function remove(payload: { reason_id: string; note: string | null }) {
  if (!removing.value) return
  try {
    await api(`/queue/${removing.value.id}/remove`, { method: 'POST', body: payload })
    removing.value = null
    toast.success('Paciente retirado de la cola.')
    await refresh()
  } catch (e) {
    listError.value = apiErrorMessage(e)
    toast.error(listError.value)
    removing.value = null
  }
}
</script>
