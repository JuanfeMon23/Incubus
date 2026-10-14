<template>
  <div class="grid gap-6 lg:grid-cols-[20rem_1fr]">
    <aside class="space-y-6">
      <section>
        <h2 class="mb-2 font-semibold">Esperando recepción ({{ waiting.length }})</h2>
        <ul class="space-y-2">
          <li v-for="e in waiting" :key="e.id">
            <UiCard padding="sm" :style="{ borderLeft: `6px solid ${e.priority.color_hex}` }">
              <p class="truncate text-sm font-medium">{{ fullName(e.patient) }}</p>
              <p class="text-xs text-text-muted">{{ e.patient.document_number }} · {{ waitingLabel(e.arrived_at) }}</p>
              <div class="mt-2 flex items-center justify-between">
                <PriorityBadge :priority="e.priority" />
                <UiButton size="sm" @click="claim(e)">Tomar</UiButton>
              </div>
            </UiCard>
          </li>
          <li v-if="!waiting.length" class="text-sm text-text-muted">Nadie en espera.</li>
        </ul>
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
          <UiFormField label="Primer nombre"><UiTextInput v-model="demo.first_name" /></UiFormField>
          <UiFormField label="Segundo nombre"><UiTextInput v-model="demo.second_name" /></UiFormField>
          <UiFormField label="Primer apellido"><UiTextInput v-model="demo.first_last_name" /></UiFormField>
          <UiFormField label="Segundo apellido"><UiTextInput v-model="demo.second_last_name" /></UiFormField>
          <UiFormField label="Fecha de nacimiento"><UiTextInput v-model="demo.birth_date" type="date" /></UiFormField>
          <UiFormField label="Lugar de nacimiento"><UiTextInput v-model="demo.birth_place" /></UiFormField>
          <UiFormField label="Sexo">
            <UiSelect v-model="demo.sex" :options="sexOptions" empty-label="—" />
          </UiFormField>
          <UiFormField label="Correo electrónico"><UiTextInput v-model="demo.email" type="email" /></UiFormField>
          <UiFormField label="Teléfono"><UiTextInput v-model="demo.phone" /></UiFormField>
          <UiFormField label="Aseguradora"><UiTextInput v-model="demo.insurer" /></UiFormField>
          <UiFormField label="Dirección de residencia" class="col-span-2">
            <UiTextInput v-model="demo.address" />
          </UiFormField>
        </div>

        <UiSection title="Exámenes">
          <UiTextInput v-model="search" placeholder="Buscar examen por nombre o código…" />
          <ul v-if="results.length" class="mt-1 max-h-48 overflow-auto rounded-md border border-border">
            <li v-for="t in results" :key="t.code">
              <button type="button" class="w-full px-3 py-1.5 text-left text-sm hover:bg-surface-muted" @click="addTest(t)">
                {{ t.name }} <span class="text-xs text-text-muted">{{ t.code }}</span>
              </button>
            </li>
          </ul>
          <ul class="mt-3 flex flex-wrap gap-2">
            <li v-for="t in chosen" :key="t.code" class="flex items-center gap-1 rounded-full bg-surface-muted px-3 py-1 text-sm">
              {{ t.name }}
              <button type="button" class="text-text-muted" :aria-label="`Quitar ${t.name}`" @click="removeTest(t.code)">×</button>
            </li>
          </ul>
        </UiSection>

        <PreconditionChecklist
          v-if="preconditions.length"
          v-model="checks"
          title="Preparación del paciente: verifique cada condición"
          :items="preconditions"
        />

        <UiAlert v-if="error" variant="danger" :message="error" />
        <UiAlert v-if="orderNumber" variant="success">
          Orden generada: <strong class="font-mono text-base">{{ orderNumber }}</strong>
        </UiAlert>

        <div class="flex justify-between">
          <UiButton variant="secondary" @click="returning = true">Devolver a pre-recepción</UiButton>
          <UiButton :disabled="!chosen.length || !checksOk" :loading="busy" @click="close">Cerrar y generar orden</UiButton>
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

const ACTOR = 'recepcion'
const sexOptions = [{ value: 'M', label: 'M' }, { value: 'F', label: 'F' }]
const api = useApi()
const { entries, refresh } = useQueueList(['pre_recepcion', 'en_atencion_recepcion'])
const waiting = computed(() => entries.value.filter((e) => e.status === 'pre_recepcion'))
const attending = computed(() => entries.value.filter((e) => e.status === 'en_atencion_recepcion'))

const currentId = ref<string | null>(null)
const current = computed(() => attending.value.find((e) => e.id === currentId.value) ?? null)
const age = computed(() => ageFrom(current.value?.patient.birth_date ?? null))

const demo = reactive({
  first_name: '', second_name: '', first_last_name: '', second_last_name: '',
  birth_date: '', birth_place: '', sex: '', email: '', phone: '', insurer: '', address: ''
})
const chosen = ref<CatalogTest[]>([])
const preconditions = ref<OrderPrecondition[]>([])
const checks = ref<CheckMap>({})
const keys = computed(() => preconditions.value.map((p) => p.key))
const checksOk = computed(() => checksComplete(keys.value, checks.value))
const search = ref('')
const results = ref<CatalogTest[]>([])
const error = ref('')
const orderNumber = ref('')
const busy = ref(false)
const returning = ref(false)
const returnReasons = ref<Reason[]>([])

onMounted(async () => {
  returnReasons.value = await api<Reason[]>('/return-reasons')
})

function select(e: QueueEntry) {
  currentId.value = e.id
  orderNumber.value = ''
  error.value = ''
  for (const k of Object.keys(demo) as (keyof typeof demo)[]) {
    demo[k] = (e.patient as unknown as Record<string, string | null>)[k] ?? ''
  }
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

async function claim(e: QueueEntry) {
  error.value = ''
  try {
    await api(`/queue/${e.id}/claim`, { method: 'POST', body: { actor: ACTOR } })
    await refresh()
    const fresh = entries.value.find((x) => x.id === e.id)
    if (fresh) select(fresh)
  } catch (err) {
    error.value = apiErrorMessage(err)
    await refresh()
  }
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, (q) => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    results.value = q.trim().length >= 2
      ? await api<CatalogTest[]>('/catalog/tests', { query: { q } })
      : []
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
  const body = Object.fromEntries(Object.entries(demo).map(([k, v]) => [k, v === '' ? null : v]))
  await api(`/patients/${current.value.patient.id}`, { method: 'PATCH', body })
}

async function close() {
  if (!current.value) return
  busy.value = true
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
    currentId.value = null
    await refresh()
  } catch (e) {
    error.value = apiErrorMessage(e)
  } finally {
    busy.value = false
  }
}

async function giveBack(payload: { reason_id: string; note: string | null }) {
  if (!current.value) return
  returning.value = false
  try {
    await saveDemographics()
    await api(`/queue/${current.value.id}/return`, { method: 'POST', body: { ...payload, actor: ACTOR } })
    currentId.value = null
    await refresh()
  } catch (e) {
    error.value = apiErrorMessage(e)
  }
}
</script>
