<template>
  <div class="grid gap-6 lg:grid-cols-[20rem_1fr]">
    <aside class="space-y-6">
      <section class="space-y-3">
        <div class="rounded-xl bg-primary-50 p-4 text-center">
          <p class="text-3xl font-bold text-primary-700">{{ waiting.length }}</p>
          <p class="text-sm text-primary-700">
            {{ waiting.length === 1 ? 'paciente en espera' : 'pacientes en espera' }}
          </p>
          <UiButton
            class="mt-3 w-full"
            size="lg"
            :disabled="!waiting.length"
            :loading="calling"
            @click="callNext"
          >
            Llamar al siguiente
          </UiButton>
          <p v-if="waiting[0]" class="mt-2 text-xs text-primary-700">
            Sigue: prioridad {{ waiting[0].priority.name.toLowerCase() }} · espera
            {{ waitingLabel(waiting[0].arrived_at) }}
          </p>
        </div>
        <div v-if="listLoading" class="flex justify-center py-2">
          <UiSpinner color="primary" label="Cargando cola" />
        </div>
      </section>

      <section>
        <h2 class="mb-2 font-semibold">En atención ({{ attending.length }})</h2>
        <ul class="space-y-2">
          <li v-for="e in attending" :key="e.id">
            <button
              type="button"
              class="w-full rounded-lg border-2 bg-surface p-3 text-left text-sm shadow-sm transition-colors"
              :class="current?.id === e.id ? 'border-primary-500' : 'border-transparent'"
              @click="select(e)"
            >
              <span class="block truncate font-medium">{{ fullName(e.patient) }}</span>
              <span class="text-xs text-text-muted">{{ e.claimed_by || 'sin asignar' }}</span>
            </button>
          </li>
        </ul>
      </section>
    </aside>

    <UiCard v-if="current">
      <div class="space-y-5">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h1 class="text-lg font-semibold">{{ fullName(current.patient) }}</h1>
            <p class="text-sm text-text-muted">
              {{ current.patient.document_type }} {{ current.patient.document_number }}
              <template v-if="age !== null"> · {{ age }} años</template>
            </p>
          </div>
          <PriorityBadge :priority="current.priority" />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <UiFormField name="first_name" label="Primer nombre" required><UiTextInput /></UiFormField>
          <UiFormField name="second_name" label="Segundo nombre"><UiTextInput /></UiFormField>
          <UiFormField name="first_last_name" label="Primer apellido" required><UiTextInput /></UiFormField>
          <UiFormField name="second_last_name" label="Segundo apellido"><UiTextInput /></UiFormField>
          <UiFormField name="birth_date" label="Fecha de nacimiento" required><UiTextInput type="date" /></UiFormField>
          <UiFormField name="birth_place" label="Lugar de nacimiento" required><UiTextInput /></UiFormField>
          <UiFormField name="sex" label="Sexo" required>
            <UiSelect :options="sexOptions" placeholder="Seleccione…" />
          </UiFormField>
          <UiFormField name="email" label="Correo electrónico" required><UiTextInput type="email" /></UiFormField>
          <UiFormField name="phone" label="Teléfono" required><UiTextInput /></UiFormField>
          <UiFormField name="insurer" label="Aseguradora" required><UiTextInput /></UiFormField>
          <UiFormField name="address" label="Dirección de residencia" class="col-span-2" required><UiTextInput /></UiFormField>
        </div>

        <UiSection title="Exámenes" description="Busque por nombre, código o abreviatura.">
          <div class="relative">
            <UiTextInput v-model="search" placeholder="Ej.: colesterol, HBSAG, ACIDO_URICO…" />
            <div
              v-if="searching"
              class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2"
            >
              <UiSpinner size="sm" color="primary" label="Buscando" />
            </div>
          </div>

          <ul
            v-if="results.length"
            class="mt-2 max-h-64 divide-y divide-border overflow-auto rounded-lg border border-border bg-surface shadow-sm"
          >
            <li v-for="t in results" :key="t.code">
              <button
                type="button"
                class="flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-primary-50 disabled:opacity-50"
                :disabled="isChosen(t.code)"
                @click="addTest(t)"
              >
                <span class="shrink-0 rounded-md bg-default-100 px-2 py-0.5 font-mono text-xs font-semibold text-default-700">
                  {{ t.code }}
                </span>
                <span class="min-w-0 flex-1 truncate">{{ t.name }}</span>
                <span v-if="t.abbreviation" class="shrink-0 text-xs text-text-muted">{{ t.abbreviation }}</span>
                <span v-if="isChosen(t.code)" class="shrink-0 text-xs font-medium text-success-700">Agregado</span>
                <span v-else class="shrink-0 text-lg leading-none text-primary-600" aria-hidden="true">+</span>
              </button>
            </li>
          </ul>
          <p
            v-else-if="search.trim().length >= 2 && !searching"
            class="mt-2 text-sm text-text-muted"
          >
            Sin resultados para «{{ search.trim() }}».
          </p>

          <div class="mt-4">
            <p class="mb-2 text-sm font-medium">
              Exámenes de la orden
              <span class="ml-1 rounded-full bg-primary-100 px-2 py-0.5 text-xs text-primary-700">{{ chosen.length }}</span>
            </p>
            <ul v-if="chosen.length" class="grid gap-2 sm:grid-cols-2">
              <li
                v-for="t in chosen"
                :key="t.code"
                class="flex items-center gap-3 rounded-lg border border-primary-200 bg-primary-50 px-3 py-2"
              >
                <span class="shrink-0 rounded-md bg-white px-2 py-0.5 font-mono text-xs font-semibold text-primary-700">
                  {{ t.code }}
                </span>
                <span class="min-w-0 flex-1 truncate text-sm">{{ t.name }}</span>
                <button
                  type="button"
                  class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-primary-700 transition-colors hover:bg-primary-100"
                  :aria-label="`Quitar ${t.name}`"
                  @click="removeTest(t.code)"
                >
                  <span aria-hidden="true">×</span>
                </button>
              </li>
            </ul>
            <p v-else class="rounded-lg border border-dashed border-border-strong p-3 text-center text-sm text-text-muted">
              Aún no hay exámenes en la orden.
            </p>
          </div>
        </UiSection>

        <PreconditionChecklist
          v-if="preconditions.length"
          v-model="checks"
          title="Preparación del paciente: verifique cada condición"
          :items="preconditions"
        />
        <UiAlert v-if="formError" variant="danger" :message="formError" />
        <UiAlert v-else-if="error" variant="danger" :message="error" />
        <UiAlert v-if="orderNumber" variant="success">
          Orden generada: <strong class="font-mono text-base">{{ orderNumber }}</strong>
        </UiAlert>

        <div class="flex justify-between">
          <UiButton variant="secondary" @click="returning = true">Devolver a pre-recepción</UiButton>
          <UiButton :disabled="!chosen.length || !checksOk" :loading="isSubmitting" @click="onClose">Cerrar y generar orden</UiButton>
        </div>
      </div>
    </UiCard>
    <UiCard v-else>
      <p class="py-10 text-center text-sm text-text-muted">Tome un paciente de la cola para iniciar la atención.</p>
    </UiCard>

    <ReasonDialog
      v-if="returning"
      title="Devolver a pre-recepción"
      confirm-label="Devolver"
      :reasons="returnReasons"
      @cancel="returning = false"
      @confirm="giveBack"
    />
  </div>
</template>

<script setup lang="ts">
import type { CatalogTest, OrderPrecondition, QueueEntry, Reason } from '../types'
import { checksComplete, emptyChecks, toCheckPayload } from '../utils/checks'
import type { CheckMap } from '../utils/checks'
import { receptionPatientSchema } from '../utils/patientSchemas'
import type { ReceptionPatientInput } from '../utils/patientSchemas'

const ACTOR = 'recepcion'
const sexOptions = [{ value: 'M', label: 'M' }, { value: 'F', label: 'F' }]
const api = useApi()
const toast = useToast()
const { entries, loading: listLoading, refresh } = useQueueList(['pre_recepcion', 'en_atencion_recepcion'])
const calling = ref(false)
const waiting = computed(() => entries.value.filter((e) => e.status === 'pre_recepcion'))
const attending = computed(() => entries.value.filter((e) => e.status === 'en_atencion_recepcion'))

const currentId = ref<string | null>(null)
const current = computed(() => attending.value.find((e) => e.id === currentId.value) ?? null)
const age = computed(() => ageFrom(current.value?.patient.birth_date ?? null))

const DEMOGRAPHIC_FIELDS = [
  'first_name', 'second_name', 'first_last_name', 'second_last_name', 'birth_date',
  'birth_place', 'sex', 'blood_type', 'email', 'phone', 'insurer', 'address'
] as const

function demographicsOf(patient: Record<string, unknown> | null): ReceptionPatientInput {
  const get = (k: string) => String((patient?.[k] as string | null | undefined) ?? '')
  return Object.fromEntries(DEMOGRAPHIC_FIELDS.map((k) => [k, get(k)])) as ReceptionPatientInput
}

// Todos obligatorios salvo segundo nombre/apellido: errores en rojo bajo cada campo.
const form = useZodForm(receptionPatientSchema, { initialValues: () => demographicsOf(null) })
const { isSubmitting, formError } = form
const chosen = ref<CatalogTest[]>([])
const preconditions = ref<OrderPrecondition[]>([])
const checks = ref<CheckMap>({})
const keys = computed(() => preconditions.value.map((p) => p.key))
const checksOk = computed(() => checksComplete(keys.value, checks.value))

const search = ref('')
const results = ref<CatalogTest[]>([])
const searching = ref(false)
const isChosen = (code: string) => chosen.value.some((c) => c.code === code)
const error = ref('')
const orderNumber = ref('')
const returning = ref(false)
const returnReasons = ref<Reason[]>([])

onMounted(async () => {
  returnReasons.value = await api<Reason[]>('/return-reasons')
})

function select(e: QueueEntry) {
  currentId.value = e.id
  orderNumber.value = ''
  error.value = ''
  form.reset(demographicsOf(e.patient as unknown as Record<string, unknown>))
  chosen.value = []
  preconditions.value = []
  // restaura el borrador (sobrevive a una devolución a pre-recepción)
  const codes = e.draft?.test_codes ?? []
  if (codes.length) void restore(codes)
}

async function restore(codes: string[]) {
  const found = await Promise.all(
    codes.map(async (c) => (await api<CatalogTest[]>('/catalog/tests', { query: { q: c } })).find((t) => t.code === c))
  )
  chosen.value = found.filter((t): t is CatalogTest => !!t)
  await loadPreconditions(chosen.value.map((t) => t.code)).catch(() => {})
}

/** Llama al siguiente paciente según prioridad y orden de llegada. */
async function callNext() {
  error.value = ''
  calling.value = true
  try {
    const entry = await api<QueueEntry>('/queue/call-next', { method: 'POST', body: { actor: ACTOR } })
    await refresh()
    const fresh = entries.value.find((x) => x.id === entry.id)
    select(fresh ?? entry)
    toast.info(`Llamando a ${fullName(entry.patient)}.`)
  } catch (err) {
    error.value = apiErrorMessage(err)
    toast.error(error.value)
    await refresh()
  } finally {
    calling.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, (q) => {
  clearTimeout(searchTimer)
  if (q.trim().length < 2) {
    results.value = []
    return
  }
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      results.value = await api<CatalogTest[]>('/catalog/tests', { query: { q: q.trim() } })
    } catch (e) {
      toast.error(apiErrorMessage(e))
    } finally {
      searching.value = false
    }
  }, 250)
})

function addTest(t: CatalogTest) {
  if (!chosen.value.some((c) => c.code === t.code)) chosen.value.push(t)
  search.value = ''
  results.value = []
  void sync()
}
function removeTest(code: string) {
  chosen.value = chosen.value.filter((t) => t.code !== code)
  void sync()
}

// Preanalíticos unificados + guardado de borrador en cada cambio de exámenes.
async function sync() {
  if (!currentId.value) return
  const codes = chosen.value.map((t) => t.code)
  try {
    await api(`/queue/${currentId.value}/draft`, { method: 'PUT', body: { test_codes: codes } })
    await loadPreconditions(codes)
  } catch (e) {
    error.value = apiErrorMessage(e)
    toast.error(error.value)
  }
}

async function loadPreconditions(codes: string[]) {
  preconditions.value = codes.length
    ? (await api<{ preconditions: OrderPrecondition[] }>('/orders/preview', {
        method: 'POST',
        body: { test_codes: codes }
      })).preconditions
    : []
  // conserva respuestas de condiciones que siguen presentes; las nuevas quedan sin responder
  const fresh = emptyChecks(keys.value)
  for (const k of keys.value) if (checks.value[k]) fresh[k] = checks.value[k]
  checks.value = fresh
}

async function saveDemographics() {
  if (!current.value) return
  const body = Object.fromEntries(
    Object.entries(form.values as Record<string, unknown>).map(([k, v]) => [k, v === '' ? null : v])
  )
  await api(`/patients/${current.value.patient.id}`, { method: 'PATCH', body })
}

// Valida el formulario (zod); los errores del backend (p. ej. missing_fields) vuelven a los campos.
const onClose = form.submit(async () => {
  if (!current.value) return
  error.value = ''
  try {
    await saveDemographics()
    const res = await api<{ order_number: string }>(`/orders/close-reception/${current.value.id}`, {
      method: 'POST',
      body: {
        test_codes: chosen.value.map((t) => t.code),
        actor: ACTOR,
        precondition_checks: toCheckPayload(keys.value, checks.value)
      }
    })
    orderNumber.value = res.order_number
    toast.success(`Orden ${res.order_number} generada. Pasa a impresión de etiquetas.`)
    currentId.value = null
    await refresh()
  } catch (e) {
    toast.error(apiErrorMessage(e))
    throw e
  }
})

async function giveBack(payload: { reason_id: string; note: string | null }) {
  if (!current.value) return
  returning.value = false
  try {
    await saveDemographics()
    await api(`/queue/${current.value.id}/return`, { method: 'POST', body: { ...payload, actor: ACTOR } })
    toast.info('Paciente devuelto a pre-recepción.')
    currentId.value = null
    await refresh()
  } catch (e) {
    error.value = apiErrorMessage(e)
    toast.error(error.value)
  }
}
</script>
