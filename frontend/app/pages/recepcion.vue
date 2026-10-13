<template>
  <div class="grid gap-6 lg:grid-cols-[20rem_1fr]">
    <!-- Cola -->
    <aside class="space-y-5">
      <section>
        <h2 class="mb-2 font-semibold">Esperando recepción ({{ waiting.length }})</h2>
        <ul class="space-y-2">
          <li
            v-for="e in waiting"
            :key="e.id"
            class="rounded-xl border border-zinc-200 bg-white p-3"
            :style="{ borderLeft: `6px solid ${e.priority.color_hex}` }"
          >
            <p class="truncate text-sm font-medium">{{ fullName(e.patient) }}</p>
            <p class="text-xs text-zinc-500">{{ e.patient.document_number }} · {{ waitingLabel(e.arrived_at) }}</p>
            <div class="mt-2 flex items-center justify-between">
              <PriorityBadge :priority="e.priority" />
              <button class="rounded-lg bg-zinc-900 px-3 py-1 text-xs text-white" @click="claim(e)">Tomar</button>
            </div>
          </li>
          <li v-if="!waiting.length" class="text-sm text-zinc-500">Nadie en espera.</li>
        </ul>
      </section>

      <section>
        <h2 class="mb-2 font-semibold">En atención ({{ attending.length }})</h2>
        <ul class="space-y-2">
          <li v-for="e in attending" :key="e.id">
            <button
              class="w-full rounded-xl border bg-white p-3 text-left text-sm"
              :class="current?.id === e.id ? 'border-zinc-900' : 'border-zinc-200'"
              @click="select(e)"
            >
              <span class="block truncate font-medium">{{ fullName(e.patient) }}</span>
              <span class="text-xs text-zinc-500">{{ e.claimed_by || 'sin asignar' }}</span>
            </button>
          </li>
        </ul>
      </section>
    </aside>

    <!-- Atención -->
    <section v-if="current" class="space-y-5 rounded-xl border border-zinc-200 bg-white p-5">
      <header class="flex items-start justify-between">
        <div>
          <h1 class="text-lg font-semibold">{{ fullName(current.patient) }}</h1>
          <p class="text-sm text-zinc-500">
            {{ current.patient.document_type }} {{ current.patient.document_number }}
            <template v-if="age !== null"> · {{ age }} años</template>
          </p>
        </div>
        <PriorityBadge :priority="current.priority" />
      </header>

      <div class="grid grid-cols-2 gap-3 text-sm">
        <label>Primer nombre<input v-model="demo.first_name" class="field"></label>
        <label>Segundo nombre<input v-model="demo.second_name" class="field"></label>
        <label>Primer apellido<input v-model="demo.first_last_name" class="field"></label>
        <label>Segundo apellido<input v-model="demo.second_last_name" class="field"></label>
        <label>Fecha de nacimiento<input v-model="demo.birth_date" type="date" class="field"></label>
        <label>Lugar de nacimiento<input v-model="demo.birth_place" class="field"></label>
        <label>Sexo
          <select v-model="demo.sex" class="field"><option value="">—</option><option>M</option><option>F</option></select>
        </label>
        <label>Correo electrónico<input v-model="demo.email" type="email" class="field"></label>
        <label>Teléfono<input v-model="demo.phone" class="field"></label>
        <label>Aseguradora<input v-model="demo.insurer" class="field"></label>
        <label class="col-span-2">Dirección de residencia<input v-model="demo.address" class="field"></label>
      </div>

      <!-- Exámenes -->
      <div>
        <h2 class="mb-2 font-semibold">Exámenes</h2>
        <input v-model="search" placeholder="Buscar examen por nombre o código…" class="field">
        <ul v-if="results.length" class="mt-1 max-h-48 overflow-auto rounded-lg border border-zinc-200">
          <li v-for="t in results" :key="t.code">
            <button class="w-full px-3 py-1.5 text-left text-sm hover:bg-zinc-100" @click="addTest(t)">
              {{ t.name }} <span class="text-xs text-zinc-500">{{ t.code }}</span>
            </button>
          </li>
        </ul>
        <ul class="mt-3 flex flex-wrap gap-2">
          <li v-for="t in chosen" :key="t.code" class="flex items-center gap-1 rounded-full bg-zinc-100 px-3 py-1 text-sm">
            {{ t.name }}
            <button class="text-zinc-500" :aria-label="`Quitar ${t.name}`" @click="removeTest(t.code)">×</button>
          </li>
        </ul>
      </div>

      <!-- Preanalíticos unificados -->
      <div v-if="preconditions.length" class="rounded-lg border border-amber-200 bg-amber-50 p-3">
        <h2 class="mb-2 text-sm font-semibold text-amber-900">Preparación del paciente</h2>
        <ul class="space-y-1 text-sm">
          <li v-for="p in preconditions" :key="p.category + p.name + p.patient_instructions">
            <strong>{{ p.name }}</strong>
            <span v-if="formatDuration(p.duration_value, p.duration_unit)"> — {{ formatDuration(p.duration_value, p.duration_unit) }}</span>
            <span v-if="p.patient_instructions" class="text-zinc-600">: {{ p.patient_instructions }}</span>
          </li>
        </ul>
      </div>

      <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      <p v-if="orderNumber" class="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
        Orden generada: <strong class="font-mono text-base">{{ orderNumber }}</strong>
      </p>

      <footer class="flex justify-between">
        <button class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" @click="returning = true">
          Devolver a pre-recepción
        </button>
        <button
          class="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          :disabled="!chosen.length || busy"
          @click="close"
        >
          Cerrar y generar orden
        </button>
      </footer>
    </section>
    <section v-else class="rounded-xl border border-dashed border-zinc-300 p-10 text-center text-sm text-zinc-500">
      Tome un paciente de la cola para iniciar la atención.
    </section>

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

const ACTOR = 'recepcion'
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
      body: { test_codes: chosen.value.map((t) => t.code), actor: ACTOR }
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

<style scoped>
.field { margin-top: 0.25rem; width: 100%; border: 1px solid #d4d4d8; border-radius: 0.5rem; padding: 0.4rem 0.5rem; }
</style>
