<template>
  <div class="grid gap-6 lg:grid-cols-[20rem_1fr]">
    <aside class="space-y-6">
      <section>
        <h2 class="mb-2 font-semibold">Esperando toma ({{ waiting.length }})</h2>
        <ul class="space-y-2">
          <li v-for="e in waiting" :key="e.id">
            <UiCard padding="sm" :style="{ borderLeft: `6px solid ${e.priority.color_hex}` }">
              <p class="truncate text-sm font-medium">{{ fullName(e.patient) }}</p>
              <p class="text-xs text-text-muted">
                Orden {{ e.order_number }} · {{ waitingLabel(e.arrived_at) }}
              </p>
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

        <UiAlert v-if="order.preconditions.length" variant="warning" title="Verificar preparación del paciente">
          <ul class="space-y-1 text-sm">
            <li v-for="p in order.preconditions" :key="p.category + p.name + p.patient_instructions">
              <strong>{{ p.name }}</strong>
              <span v-if="formatDuration(p.duration_value, p.duration_unit)">
                — {{ formatDuration(p.duration_value, p.duration_unit) }}
              </span>
              <span v-if="p.patient_instructions">: {{ p.patient_instructions }}</span>
            </li>
          </ul>
        </UiAlert>

        <UiSection title="Tubos a tomar" description="En orden de extracción.">
          <ul class="space-y-2">
            <li
              v-for="s in order.samples"
              :key="s.id"
              class="flex items-start gap-3 rounded-lg border border-border p-3"
              :class="s.collected_at ? 'bg-success-50' : 'bg-surface'"
            >
              <span
                class="mt-1 h-5 w-5 shrink-0 rounded-full border border-border-strong"
                :style="{ backgroundColor: s.cap_color_hex || '#e4e4e7' }"
              />
              <div class="min-w-0 flex-1">
                <p class="font-medium">
                  {{ s.name }}
                  <span v-if="formatVolume(s.required_volume_ml)" class="text-sm font-normal text-text-muted">
                    · {{ formatVolume(s.required_volume_ml) }}
                  </span>
                </p>
                <p class="text-xs text-text-muted">Exámenes: {{ s.test_codes.join(', ') }}</p>
                <p v-if="s.collection_instructions" class="text-xs">{{ s.collection_instructions }}</p>
              </div>
              <UiCheckbox
                :model-value="!!s.collected_at"
                label="Tomada"
                @update:model-value="toggle(s, $event)"
              />
            </li>
          </ul>
        </UiSection>

        <UiAlert v-if="error" variant="danger" :message="error" />

        <div class="flex justify-between">
          <UiButton variant="secondary" @click="returning = true">Devolver a espera</UiButton>
          <UiButton :disabled="!allCollected(order.samples)" :loading="busy" @click="finish">
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
import type { OrderDetail, OrderSample, QueueEntry, Reason } from '../types'

const ACTOR = 'toma-muestras'
const api = useApi()
const { entries, refresh } = useQueueList(['en_espera_toma_muestras', 'en_atencion_toma_muestras'])
const waiting = computed(() => entries.value.filter((e) => e.status === 'en_espera_toma_muestras'))
const attending = computed(() => entries.value.filter((e) => e.status === 'en_atencion_toma_muestras'))

const currentId = ref<string | null>(null)
const current = computed(() => attending.value.find((e) => e.id === currentId.value) ?? null)
const order = ref<OrderDetail | null>(null)
const error = ref('')
const busy = ref(false)
const returning = ref(false)
const returnReasons = ref<Reason[]>([])

onMounted(async () => {
  returnReasons.value = await api<Reason[]>('/return-reasons')
})

async function select(e: QueueEntry) {
  currentId.value = e.id
  error.value = ''
  order.value = null
  try {
    order.value = await api<OrderDetail>(`/orders/by-entry/${e.id}`)
  } catch (err) {
    error.value = apiErrorMessage(err)
  }
}

async function claim(e: QueueEntry) {
  error.value = ''
  try {
    await api(`/queue/${e.id}/claim`, { method: 'POST', body: { actor: ACTOR } })
    await refresh()
    const fresh = entries.value.find((x) => x.id === e.id)
    if (fresh) await select(fresh)
  } catch (err) {
    error.value = apiErrorMessage(err)
    await refresh()
  }
}

async function toggle(sample: OrderSample, collected: boolean) {
  if (!order.value) return
  try {
    const updated = await api<OrderSample>(
      `/orders/samples/${sample.id}/${collected ? 'collect' : 'uncollect'}`,
      { method: 'POST', body: { actor: ACTOR } }
    )
    order.value = {
      ...order.value,
      samples: order.value.samples.map((s) => (s.id === updated.id ? updated : s))
    }
  } catch (err) {
    error.value = apiErrorMessage(err)
  }
}

async function finish() {
  if (!current.value) return
  busy.value = true
  error.value = ''
  try {
    await api(`/queue/${current.value.id}/finish-sampling`, {
      method: 'POST',
      body: { actor: ACTOR }
    })
    currentId.value = null
    order.value = null
    await refresh()
  } catch (err) {
    error.value = apiErrorMessage(err)
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
    currentId.value = null
    order.value = null
    await refresh()
  } catch (err) {
    error.value = apiErrorMessage(err)
  }
}
</script>
