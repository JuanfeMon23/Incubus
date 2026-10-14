<template>
  <div class="grid gap-6 lg:grid-cols-[20rem_1fr]">
    <aside class="space-y-6">
      <UiFormField label="Profesional" required>
        <UiSelect
          v-model="professionalId"
          :options="staffOptions"
          placeholder="Seleccione quién atiende…"
        />
      </UiFormField>
      <section>
        <h2 class="mb-2 font-semibold">Mi cola de espera ({{ waiting.length }})</h2>
        <ul class="space-y-2">
          <li v-for="e in waiting" :key="e.id">
            <UiCard padding="sm" :style="{ borderLeft: `6px solid ${e.priority.color_hex}` }">
              <p class="truncate text-sm font-medium">{{ fullName(e.patient) }}</p>
              <p class="text-xs text-text-muted">
                Orden {{ e.order_number }} · {{ waitingLabel(e.arrived_at) }}
              </p>
              <div class="mt-2 flex items-center justify-between">
                <PriorityBadge :priority="e.priority" />
                <UiButton size="sm" :disabled="!professionalId" :loading="claimingId === e.id" @click="claim(e)">
                  Tomar
                </UiButton>
              </div>
            </UiCard>
          </li>
          <li v-if="listLoading" class="flex justify-center py-4">
            <UiSpinner color="primary" label="Cargando cola" />
          </li>
          <li v-else-if="!waiting.length" class="text-sm text-text-muted">
            {{ professionalId ? 'Sin pacientes asignados.' : 'Seleccione un profesional.' }}
          </li>
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
              <span class="text-xs text-text-muted">
                Orden {{ e.order_number }} · {{ e.claimed_by || 'sin asignar' }}
              </span>
            </button>
          </li>
        </ul>
      </section>
    </aside>

    <UiCard v-if="current && order">
      <div class="space-y-5">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h1 class="text-lg font-semibold">{{ fullName(current.patient) }}</h1>
            <p class="text-sm text-text-muted">
              {{ current.patient.document_type }} {{ current.patient.document_number }} ·
              Orden <span class="font-mono">{{ order.order_number }}</span>
            </p>
          </div>
          <PriorityBadge :priority="current.priority" />
        </div>

        <PreconditionChecklist
          v-if="order.preconditions.length"
          v-model="checks"
          title="Segunda verificación de la preparación del paciente"
          :items="order.preconditions"
          :previous="receptionResults"
        />

        <UiSection title="Tubos a tomar" description="En orden de extracción; marque cada tubo al tomarlo.">
          <ul class="space-y-3">
            <li v-for="s in order.samples" :key="s.id">
              <SampleTubeCard :sample="s">
                <template #actions>
                  <UiCheckbox
                    :model-value="!!s.collected_at"
                    :disabled="togglingId === s.id"
                    label="Tomado"
                    @update:model-value="toggle(s, $event)"
                  />
                </template>
              </SampleTubeCard>
            </li>
          </ul>
          <p class="mt-2 text-xs text-text-muted">
            {{ order.samples.filter((s) => s.collected_at).length }} de {{ order.samples.length }} tubos tomados
          </p>
        </UiSection>

        <UiAlert v-if="error" variant="danger" :message="error" />

        <div class="flex justify-between">
          <UiButton variant="secondary" @click="returning = true">Devolver a espera</UiButton>
          <UiButton :disabled="!allCollected(order.samples) || !checksOk" :loading="busy" @click="finish">
            Finalizar toma
          </UiButton>
        </div>
      </div>
    </UiCard>
    <UiCard v-else>
      <p class="py-10 text-center text-sm text-text-muted">
        Tome un paciente de la cola para iniciar la toma de muestras.
      </p>
    </UiCard>

    <ReasonDialog
      v-if="returning"
      title="Devolver a espera de toma de muestras"
      confirm-label="Devolver"
      :reasons="returnReasons"
      @cancel="returning = false"
      @confirm="giveBack"
    />
  </div>
</template>

<script setup lang="ts">
import type { OrderDetail, OrderSample, QueueEntry, Reason, StaffMember } from '../types'
import { checksComplete, emptyChecks, toCheckPayload } from '../utils/checks'
import type { CheckMap } from '../utils/checks'

const ACTOR = 'toma-muestras'
const api = useApi()
const toast = useToast()
const { entries, loading: listLoading, refresh } = useQueueList(['en_espera_toma_muestras', 'en_atencion_toma_muestras'])
const claimingId = ref<string | null>(null)
const togglingId = ref<string | null>(null)

// Profesional que atiende (se recuerda en este navegador).
const staff = ref<StaffMember[]>([])
const staffOptions = computed(() => staff.value.map((s) => ({ value: s.id, label: s.name })))
const professionalId = ref('')
const professional = computed(() => staff.value.find((s) => s.id === professionalId.value) ?? null)
const mine = computed(() =>
  entries.value.filter((e) => e.assigned_professional_id === professionalId.value)
)
const waiting = computed(() => mine.value.filter((e) => e.status === 'en_espera_toma_muestras'))
const attending = computed(() => mine.value.filter((e) => e.status === 'en_atencion_toma_muestras'))

const checks = ref<CheckMap>({})
const checkKeys = computed(() => order.value?.preconditions.map((p) => p.key) ?? [])
const checksOk = computed(() => checksComplete(checkKeys.value, checks.value))
const receptionResults = computed(() =>
  Object.fromEntries((order.value?.preconditions ?? []).map((p) => [p.key, p.reception_met ?? null]))
)

const currentId = ref<string | null>(null)
const current = computed(() => attending.value.find((e) => e.id === currentId.value) ?? null)
const order = ref<OrderDetail | null>(null)
const error = ref('')
const busy = ref(false)
const returning = ref(false)
const returnReasons = ref<Reason[]>([])

onMounted(async () => {
  returnReasons.value = await api<Reason[]>('/return-reasons')
  staff.value = await api<StaffMember[]>('/catalog/staff')
  try {
    professionalId.value = localStorage.getItem('incubus.professional') ?? ''
  } catch {
    /* almacenamiento no disponible */
  }
})

watch(professionalId, (id) => {
  currentId.value = null
  order.value = null
  try {
    localStorage.setItem('incubus.professional', id)
  } catch {
    /* almacenamiento no disponible */
  }
})

async function select(e: QueueEntry) {
  currentId.value = e.id
  error.value = ''
  order.value = null
  try {
    order.value = await api<OrderDetail>(`/orders/by-entry/${e.id}`)
    const initial = emptyChecks(order.value.preconditions.map((p) => p.key))
    for (const p of order.value.preconditions) {
      if (p.sampling_met !== null && p.sampling_met !== undefined) {
        initial[p.key] = { met: p.sampling_met, note: p.sampling_note ?? '' }
      }
    }
    checks.value = initial
  } catch (err) {
    error.value = apiErrorMessage(err)
    toast.error(error.value)
  }
}

async function claim(e: QueueEntry) {
  error.value = ''
  claimingId.value = e.id
  try {
    await api(`/queue/${e.id}/claim`, {
      method: 'POST',
      body: { actor: professional.value?.name ?? ACTOR, professional_id: professionalId.value }
    })
    await refresh()
    const fresh = entries.value.find((x) => x.id === e.id)
    if (fresh) await select(fresh)
  } catch (err) {
    error.value = apiErrorMessage(err)
    toast.error(error.value)
    await refresh()
  } finally {
    claimingId.value = null
  }
}

async function toggle(sample: OrderSample, collected: boolean) {
  if (!order.value) return
  togglingId.value = sample.id
  try {
    const updated = await api<OrderSample>(
      `/orders/samples/${sample.id}/${collected ? 'collect' : 'uncollect'}`,
      { method: 'POST', body: { actor: ACTOR } }
    )
    order.value = {
      ...order.value,
      samples: order.value.samples.map((s) => (s.id === updated.id ? updated : s))
    }
    if (collected) toast.success(`Tubo «${sample.name}» marcado como tomado.`)
  } catch (err) {
    error.value = apiErrorMessage(err)
    toast.error(error.value)
  } finally {
    togglingId.value = null
  }
}

async function finish() {
  if (!current.value) return
  busy.value = true
  error.value = ''
  try {
    await api(`/orders/by-entry/${current.value.id}/precondition-checks`, {
      method: 'POST',
      body: {
        stage: 'sampling',
        actor: professional.value?.name ?? ACTOR,
        checks: toCheckPayload(checkKeys.value, checks.value)
      }
    })
    await api(`/queue/${current.value.id}/finish-sampling`, {
      method: 'POST',
      body: { actor: ACTOR }
    })
    toast.success('Toma de muestras finalizada.')
    currentId.value = null
    order.value = null
    await refresh()
  } catch (err) {
    error.value = apiErrorMessage(err)
    toast.error(error.value)
  } finally {
    busy.value = false
  }
}

async function giveBack(payload: { reason_id: string; note: string | null }) {
  if (!current.value) return
  returning.value = false
  try {
    await api(`/queue/${current.value.id}/return`, {
      method: 'POST',
      body: { ...payload, actor: ACTOR }
    })
    toast.info('Paciente devuelto a espera de toma de muestras.')
    currentId.value = null
    order.value = null
    await refresh()
  } catch (err) {
    error.value = apiErrorMessage(err)
    toast.error(error.value)
  }
}
</script>
