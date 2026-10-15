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
          <UiFormField name="document_type" label="Tipo de documento" required>
            <UiSelect :options="documentTypeOptions" placeholder="Seleccione…" />
          </UiFormField>
          <UiFormField name="document_number" label="Número de documento" required><UiTextInput /></UiFormField>
          <UiFormField name="sex" label="Sexo">
            <UiSelect :options="sexOptions" empty-label="—" />
          </UiFormField>
          <UiFormField name="first_name" label="Primer nombre" required><UiTextInput /></UiFormField>
          <UiFormField name="second_name" label="Segundo nombre"><UiTextInput /></UiFormField>
          <UiFormField name="first_last_name" label="Primer apellido" required><UiTextInput /></UiFormField>
          <UiFormField name="second_last_name" label="Segundo apellido"><UiTextInput /></UiFormField>
          <UiFormField name="birth_date" label="Nacimiento"><UiTextInput type="date" :max="today" /></UiFormField>
          <UiFormField name="blood_type" label="RH">
            <UiSelect :options="bloodOptions" empty-label="—" />
          </UiFormField>
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
      <ul class="space-y-3">
        <li v-for="e in entries" :key="e.id">
          <QueueEntryCard :entry="e">
            <template #actions>
              <UiButton size="sm" variant="danger-ghost" @click="removing = e">Retirar</UiButton>
            </template>
          </QueueEntryCard>
        </li>
        <li v-if="!entries.length && !listLoading" class="rounded-xl border border-dashed border-border-strong p-8 text-center text-sm text-text-muted">
          Sin pacientes en espera.
        </li>
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
import { BLOOD_TYPES, intakePatientSchema, todayISO } from '../utils/patientSchemas'

const today = todayISO()
const bloodOptions = BLOOD_TYPES.map((v) => ({ value: v, label: v }))
const documentTypes = ref<Reason[]>([])
const documentTypeOptions = computed(() =>
  documentTypes.value.map((d) => ({ value: d.code, label: `${d.code} · ${d.name}` }))
)
const sexOptions = [{ value: 'M', label: 'M' }, { value: 'F', label: 'F' }]
const api = useApi()
const toast = useToast()
const { entries, error: listError, loading: listLoading, refresh } = useQueueList(['pre_recepcion'])

const priorities = ref<Priority[]>([])
const removalReasons = ref<Reason[]>([])
onMounted(async () => {
  ;[priorities.value, removalReasons.value, documentTypes.value] = await Promise.all([
    api<Priority[]>('/priorities'),
    api<Reason[]>('/removal-reasons'),
    api<Reason[]>('/document-types')
  ])
  priorityId.value = priorities.value.find((p) => p.code === 'media')?.id ?? ''
})

const blank = () => ({
  document_type: 'CC',
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
      document_type: 'CC',
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

// Si el documento ya existe en la BD, se cargan todos sus datos automáticamente.
let lookupTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => [form.values.document_type, form.values.document_number] as const,
  ([type, number]) => {
    clearTimeout(lookupTimer)
    if (!type || !number || String(number).trim().length < 3) return
    lookupTimer = setTimeout(async () => {
      try {
        const found = await api<Record<string, string | null>>('/patients/lookup', {
          query: { document_type: type, document_number: String(number).trim() }
        })
        const text = (k: string) => found[k] ?? ''
        form.setValues({
          first_name: text('first_name'),
          second_name: text('second_name'),
          first_last_name: text('first_last_name'),
          second_last_name: text('second_last_name'),
          sex: text('sex') as '' | 'M' | 'F',
          birth_date: text('birth_date'),
          blood_type: text('blood_type')
        })
        toast.info('El paciente ya existe: se cargaron sus datos.')
      } catch {
        /* no existe: se digitan los datos */
      }
    }, 450)
  }
)

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
