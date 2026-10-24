<template>
  <div class="grid gap-6 lg:grid-cols-[20rem_1fr]">
    <aside class="space-y-6">
      <section v-if="canCall || canSeeWaiting" class="space-y-3">
        <div class="rounded-xl bg-primary-50 p-4 text-center">
          <template v-if="canSeeWaiting">
            <p class="text-3xl font-bold text-primary-700">{{ waiting.length }}</p>
            <p class="text-sm text-primary-700">
              {{ waiting.length === 1 ? 'paciente en espera' : 'pacientes en espera' }}
            </p>
          </template>
          <UiButton
            v-if="canCall"
            class="mt-3 w-full"
            size="lg"
            :disabled="canSeeWaiting && !waiting.length"
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
        <div v-if="canSeeWaiting && listLoading" class="flex justify-center py-2">
          <UiSpinner color="primary" label="Cargando cola" />
        </div>
        <ul v-else-if="canSeeWaiting && waiting.length" class="space-y-2">
          <li v-for="(e, i) in waiting.slice(0, 3)" :key="e.id" :class="i === 0 ? '' : 'opacity-80'">
            <QueueEntryCard :entry="e" compact>
              <template v-if="i === 0" #chips>
                <span class="rounded-full bg-primary-600 px-2 py-0.5 font-semibold text-white">Siguiente</span>
              </template>
            </QueueEntryCard>
          </li>
          <li v-if="waiting.length > 3" class="text-center text-xs text-text-muted">
            y {{ waiting.length - 3 }} más en espera
          </li>
        </ul>
      </section>

      <section>
        <h2 class="mb-2 font-semibold">En atención ({{ attending.length }})</h2>
        <ul class="space-y-2">
          <li v-for="e in attending" :key="e.id">
            <QueueEntryCard :entry="e" compact selectable show-claimed-by :selected="current?.id === e.id" @select="select(e)" />
          </li>
          <li v-if="!attending.length" class="text-sm text-text-muted">Nadie en atención.</li>
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

        <UiAlert :variant="ownsTurn ? 'info' : 'warning'">
          <template v-if="ownsTurn">Atiende: {{ current.claimed_by || 'sin registro' }}.</template>
          <template v-else>{{ hint('editar la atención, verificar la preparación, devolverlo o cerrar la recepción') }}</template>
        </UiAlert>

        <UiAlert v-if="!canEdit" variant="info">
          Solo lectura: no tienes permiso para «{{ editPatientName }}».
        </UiAlert>

        <!-- Sin edit-patient todo el formulario queda en solo lectura (un fieldset deshabilitado apaga sus controles). -->
        <fieldset :disabled="!canEdit || !ownsTurn" class="m-0 min-w-0 space-y-5 border-0 p-0">
        <div class="grid grid-cols-2 gap-3">
          <UiFormField name="document_type" label="Tipo de documento" required>
            <UiSelect :options="documentTypeOptions" placeholder="Seleccione…" />
          </UiFormField>
          <UiFormField name="document_number" label="Número de documento" required><UiTextInput /></UiFormField>
          <UiFormField name="first_name" label="Primer nombre" required><UiTextInput /></UiFormField>
          <UiFormField name="second_name" label="Segundo nombre"><UiTextInput /></UiFormField>
          <UiFormField name="first_last_name" label="Primer apellido" required><UiTextInput /></UiFormField>
          <UiFormField name="second_last_name" label="Segundo apellido"><UiTextInput /></UiFormField>
          <UiFormField name="birth_date" label="Fecha de nacimiento" required><UiTextInput type="date" :max="today" /></UiFormField>
          <UiFormField name="birth_place" label="Lugar de nacimiento" required><UiTextInput /></UiFormField>
          <UiFormField name="sex" label="Sexo" required>
            <UiSelect :options="sexOptions" placeholder="Seleccione…" />
          </UiFormField>
          <UiFormField name="blood_type" label="RH" required>
            <UiSelect :options="bloodOptions" placeholder="Seleccione…" />
          </UiFormField>
          <UiFormField name="email" label="Correo electrónico" required><UiTextInput type="email" /></UiFormField>
          <UiFormField name="phone" label="Teléfono" required hint="Solo números."><UiTextInput inputmode="numeric" maxlength="15" /></UiFormField>
          <UiFormField name="insurer" label="Aseguradora"><UiTextInput /></UiFormField>
          <UiFormField name="address" label="Dirección de residencia" class="col-span-2" required><UiTextInput /></UiFormField>
        </div>

        <UiSection title="Exámenes" description="Busque por nombre, código o abreviatura.">
          <div v-if="canEdit" class="relative">
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
            v-else-if="canEdit && search.trim().length >= 2 && !searching"
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
                  v-if="canEdit"
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
          :disabled="!ownsTurn"
          :disabled-hint="hint('verificar la preparación')"
          :items="preconditions"
        />
        </fieldset>
        <UiAlert v-if="formError" variant="danger" :message="formError" />
        <UiAlert v-else-if="error" variant="danger" :message="error" />
        <UiAlert v-if="orderNumber" variant="success">
          Orden generada: <strong class="font-mono text-base">{{ orderNumber }}</strong>
        </UiAlert>

        <div class="flex justify-between">
          <UiButton
            v-if="canReturn"
            variant="secondary"
            :disabled="!ownsTurn"
            :title="ownsTurn ? undefined : hint('devolverlo a pre-recepción')"
            @click="returning = true"
          >Devolver a pre-recepción</UiButton>
          <span v-else />
          <UiButton
            v-if="canClose"
            :disabled="!ownsTurn || !chosen.length || !checksOk"
            :title="ownsTurn ? undefined : hint('cerrar la recepción')"
            :loading="isSubmitting"
            @click="onClose"
          >Cerrar y generar orden</UiButton>
        </div>
      </div>
    </UiCard>
    <UiCard v-else>
      <p class="py-10 text-center text-sm text-text-muted">Tome un paciente de la cola para iniciar la atención.</p>
    </UiCard>

    <ActivationReceiptModal
      v-if="receipt"
      :order-number="receipt.orderNumber"
      :activation-code="receipt.activationCode"
      @close="receipt = null"
    />
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
import { BLOOD_TYPES, digitsOnly, receptionPatientSchema, todayISO } from '../utils/patientSchemas'
import type { ReceptionPatientInput } from '../utils/patientSchemas'
import { isNotTurnOwnerError } from '../utils/turnOwnership'

// Pantalla: reception.view. Cada acción exige su tag; sin edit-patient el formulario es de solo lectura.
// La lista de espera (pre-recepción) solo se ve con pre-reception.view.
definePageMeta({ leo: { tag: TAGS.reception.view } })
const canCall = useCan(TAGS.reception.callNext)
const canEdit = useCan(TAGS.reception.editPatient)
const canClose = useCan(TAGS.reception.closeReception)
const canReturn = useCan(TAGS.reception.return)
const canSeeWaiting = useCan(TAGS.preReception.view)
const editPatientName = permissionName(TAGS.reception.editPatient)

const today = todayISO()
const bloodOptions = BLOOD_TYPES.map((v) => ({ value: v, label: v }))
const documentTypes = ref<Reason[]>([])
const documentTypeOptions = computed(() =>
  documentTypes.value.map((d) => ({ value: d.code, label: `${d.code} · ${d.name}` }))
)
const sexOptions = [{ value: 'M', label: 'M' }, { value: 'F', label: 'F' }]
const api = useLeoAppApi()
const toast = useToast()
const { entries, loading: listLoading, refresh } = useQueueList(['pre_recepcion', 'en_atencion_recepcion'])
const calling = ref(false)
const waiting = computed(() => entries.value.filter((e) => e.status === 'pre_recepcion'))
const attending = computed(() => entries.value.filter((e) => e.status === 'en_atencion_recepcion'))

const currentId = ref<string | null>(null)
const current = computed(() => attending.value.find((e) => e.id === currentId.value) ?? null)
// Solo quien llamó al paciente (o un supervisor) edita, verifica, devuelve o cierra; retirar no exige ser dueño.
const { ownsTurn, hint } = useTurnOwnership(current)
const age = computed(() => ageFrom(current.value?.patient.birth_date ?? null))

const DEMOGRAPHIC_FIELDS = [
  'document_type', 'document_number', 'first_name', 'second_name', 'first_last_name', 'second_last_name', 'birth_date',
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
const receipt = ref<{ orderNumber: string; activationCode: string } | null>(null)
const returning = ref(false)
const returnReasons = ref<Reason[]>([])

onMounted(async () => {
  ;[returnReasons.value, documentTypes.value] = await Promise.all([
    api.get<Reason[]>('/return-reasons'),
    api.get<Reason[]>('/document-types')
  ])
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
    codes.map(async (c) => (await api.get<CatalogTest[]>('/catalog/tests', { query: { q: c } })).find((t) => t.code === c))
  )
  chosen.value = found.filter((t): t is CatalogTest => !!t)
  await loadPreconditions(chosen.value.map((t) => t.code)).catch(() => {})
}

/** Llama al siguiente paciente según prioridad y orden de llegada. */
async function callNext() {
  error.value = ''
  calling.value = true
  try {
    const entry = await api.post<QueueEntry>('/queue/call-next')
    await refresh()
    const fresh = entries.value.find((x) => x.id === entry.id)
    select(fresh ?? entry)
    toast.info(`Llamando a ${fullName(entry.patient)}.`)
  } catch (err) {
    error.value = leoErrorMessage(err)
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
      results.value = await api.get<CatalogTest[]>('/catalog/tests', { query: { q: q.trim() } })
    } catch (e) {
      toast.error(leoErrorMessage(e))
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
  if (!currentId.value || !ownsTurn.value) return
  const codes = chosen.value.map((t) => t.code)
  try {
    await api.put(`/queue/${currentId.value}/draft`, { test_codes: codes })
    await loadPreconditions(codes)
  } catch (e) {
    await failWith(e)
  }
}

async function loadPreconditions(codes: string[]) {
  preconditions.value = codes.length
    ? (await api.post<{ preconditions: OrderPrecondition[] }>('/orders/preview', { test_codes: codes })).preconditions
    : []
  // conserva respuestas de condiciones que siguen presentes; las nuevas quedan sin responder
  const fresh = emptyChecks(keys.value)
  for (const k of keys.value) if (checks.value[k]) fresh[k] = checks.value[k]
  checks.value = fresh
}

async function saveDemographics() {
  if (!current.value || !canEdit.value || !ownsTurn.value) return
  const body = Object.fromEntries(
    Object.entries(form.values as Record<string, unknown>).map(([k, v]) => [k, v === '' ? null : v])
  )
  await api.patch(`/patients/${current.value.patient.id}`, body)
}

// Teléfono: solo números (se descartan letras y símbolos al escribir o pegar).
watch(
  () => form.values.phone,
  (v) => {
    const clean = digitsOnly(String(v ?? ''))
    if (clean !== (v ?? '')) form.setFieldValue('phone', clean)
  }
)

// Si el documento digitado ya existe en la BD (otro paciente), se avisa y se
// cargan sus datos de contacto; el paciente en atención conserva su registro.
let lookupTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => [form.values.document_type, form.values.document_number] as const,
  ([type, number]) => {
    clearTimeout(lookupTimer)
    const patient = current.value?.patient
    if (!patient || !type || !number || String(number).trim().length < 3) return
    if (type === patient.document_type && number === patient.document_number) return
    lookupTimer = setTimeout(async () => {
      try {
        const found = await api.get<Record<string, string | null>>('/patients/lookup', { query: { document_type: type, document_number: String(number).trim() } })
        if (found.id !== patient.id) {
          toast.warning('Ese documento ya pertenece a otro paciente registrado. Se cargaron sus datos.')
          form.setValues({ ...demographicsOf(found as Record<string, unknown>) })
        }
      } catch {
        /* documento nuevo: se actualizará el del paciente en atención */
      }
    }, 450)
  }
)

// Valida el formulario (zod); los errores del backend (p. ej. missing_fields) vuelven a los campos.
const onClose = form.submit(async () => {
  if (!current.value) return
  error.value = ''
  try {
    await saveDemographics()
    const res = await api.post<{ order_number: string; activation_code?: string | null }>(`/orders/close-reception/${current.value.id}`, {
        test_codes: chosen.value.map((t) => t.code),
        precondition_checks: toCheckPayload(keys.value, checks.value)
      })
    orderNumber.value = res.order_number
    // Solo en memoria: se descarta al cerrar el modal (el backend no vuelve a mostrarlo).
    if (res.activation_code) receipt.value = { orderNumber: res.order_number, activationCode: res.activation_code }
    toast.success(`Orden ${res.order_number} generada. Pasa a impresión de etiquetas.`)
    currentId.value = null
    await refresh()
  } catch (e) {
    toast.error(leoErrorMessage(e))
    if (isNotTurnOwnerError(e)) {
      // Mensaje del backend tal cual (el mapeo genérico del formulario lo reemplazaría) y re-sincroniza.
      error.value = leoErrorMessage(e)
      await refresh()
      return
    }
    throw e
  }
})

async function giveBack(payload: { reason_id: string; note: string | null }) {
  if (!current.value) return
  returning.value = false
  try {
    await saveDemographics()
    await api.post(`/queue/${current.value.id}/return`, payload)
    toast.info('Paciente devuelto a pre-recepción.')
    currentId.value = null
    await refresh()
  } catch (e) {
    await failWith(e)
  }
}

/** Muestra el error legible; si el turno es de otra persona (403 `not_turn_owner`), re-sincroniza la lista. */
async function failWith(e: unknown) {
  error.value = leoErrorMessage(e)
  toast.error(error.value)
  if (isNotTurnOwnerError(e)) await refresh()
}
</script>
