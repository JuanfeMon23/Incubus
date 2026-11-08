<template>
  <div class="grid gap-6 lg:grid-cols-[22rem_1fr]">
    <aside class="space-y-3">
      <h2 class="font-semibold">Muestras por recibir ({{ orders.length }})</h2>
      <UiTextInput
        v-model="search"
        placeholder="Buscar por orden, documento o paciente…"
        aria-label="Buscar orden"
      />
      <div v-if="loading" class="flex justify-center py-6">
        <UiSpinner size="lg" color="primary" label="Cargando muestras" />
      </div>
      <ul v-else class="space-y-2">
        <li v-for="order in orders" :key="order.entry_id">
          <button
            type="button"
            class="w-full rounded-lg border-2 bg-surface p-3 text-left shadow-sm transition-colors"
            :class="current?.entry_id === order.entry_id ? 'border-primary-500' : 'border-transparent'"
            @click="currentId = order.entry_id"
          >
            <span class="block truncate font-medium">{{ order.patient_name }}</span>
            <span class="text-xs text-text-muted">
              Orden <span class="font-mono">{{ order.order_number }}</span> · {{ order.document }}
            </span>
            <span class="mt-1 flex items-center gap-1 text-xs">
              <span
                v-for="sample in order.samples"
                :key="sample.id"
                class="h-3 w-3 rounded-full border border-border-strong"
                :class="sample.received_at ? 'opacity-100' : 'opacity-60'"
                :style="{ backgroundColor: sample.cap_color_hex || '#e4e4e7' }"
              />
              <span class="ml-1 text-text-muted">{{ order.pending }} por recibir</span>
            </span>
          </button>
        </li>
        <li v-if="!orders.length" class="text-sm text-text-muted">
          No hay muestras esperando recepción en el laboratorio.
        </li>
      </ul>
    </aside>

    <UiCard v-if="current">
      <div class="space-y-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h1 class="text-lg font-semibold">{{ current.patient_name }}</h1>
            <p class="text-sm text-text-muted">
              {{ current.document }} · Orden <span class="font-mono">{{ current.order_number }}</span>
            </p>
          </div>
          <QueueHistoryButton :entry-id="current.entry_id" />
        </div>

        <UiAlert variant="info">
          Confirme la llegada de cada tubo al laboratorio. Cuando estén todos, la orden pasa a
          validación de resultados.
        </UiAlert>

        <ul class="space-y-3">
          <li v-for="sample in current.samples" :key="sample.id">
            <SampleTubeCard
              :sample="toSample(sample)"
            >
              <template #actions>
                <UiButton
                  v-if="sample.received_at ? canUnreceive : canReceive"
                  :variant="sample.received_at ? 'secondary' : 'primary'"
                  size="sm"
                  :loading="busyId === sample.id"
                  @click="toggle(sample)"
                >
                  {{ sample.received_at ? 'Deshacer' : 'Marcar recibido' }}
                </UiButton>
              </template>
            </SampleTubeCard>
          </li>
        </ul>

        <div v-if="canReceive" class="flex justify-end">
          <UiButton :disabled="!current.pending" :loading="busyAll" @click="receiveAll">
            Recibir todos los tubos
          </UiButton>
        </div>
      </div>
    </UiCard>
    <UiCard v-else>
      <p class="py-10 text-center text-sm text-text-muted">
        Seleccione una orden para confirmar la entrada de sus tubos al laboratorio.
      </p>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import type { LabReceptionOrder, LabReceptionSample, OrderSample } from '../types'

// Pantalla: lab-reception.view. Recibir y deshacer exigen cada uno su tag.
definePageMeta({ leo: { tag: TAGS.labReception.view } })
const canReceive = useCan(TAGS.labReception.receive)
const canUnreceive = useCan(TAGS.labReception.unreceive)
const api = useLeoAppApi()
const toast = useToast()

const orders = ref<LabReceptionOrder[]>([])
const loading = ref(true)
const search = ref('')
const currentId = ref<string | null>(null)
const busyId = ref<string | null>(null)
const busyAll = ref(false)
const current = computed(() => orders.value.find((order) => order.entry_id === currentId.value) ?? null)

async function load() {
  try {
    orders.value = await api.get<LabReceptionOrder[]>('/lab/reception', { query: search.value.trim() ? { q: search.value.trim() } : {} })
  } catch (caughtError) {
    toast.error(leoErrorMessage(caughtError))
  } finally {
    loading.value = false
  }
}

onMounted(load)
// Tubos recibidos o cambios de etapa (toma finalizada -> laboratorio) refrescan la lista.
useQueueRefresh(['toma_finalizada', 'en_laboratorio'], load)
let timer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
})

/** Adapta el tubo de recepción al formato de la tarjeta compartida. */
function toSample(sample: LabReceptionSample): OrderSample {
  return {
    id: sample.id,
    sample_type_code: '',
    name: sample.name,
    cap_color_hex: sample.cap_color_hex,
    draw_order: null,
    collection_instructions: null,
    required_volume_ml: null,
    test_codes: sample.test_codes,
    area_route: sample.area_route,
    labels_printed_at: null,
    collected_at: sample.received_at,
    collected_by: sample.received_by
  }
}

async function toggle(sample: LabReceptionSample) {
  busyId.value = sample.id
  try {
    const action = sample.received_at ? 'unreceive' : 'receive'
    const res = await api.post<{ entry_status: string }>(`/orders/samples/${sample.id}/${action}`)
    if (res.entry_status === 'en_laboratorio') {
      toast.success(`Orden ${current.value?.order_number} recibida: pasa a validación de resultados.`)
      currentId.value = null
    }
    await load()
  } catch (caughtError) {
    toast.error(leoErrorMessage(caughtError))
  } finally {
    busyId.value = null
  }
}

async function receiveAll() {
  if (!current.value) return
  busyAll.value = true
  const number = current.value.order_number
  try {
    for (const sample of current.value.samples.filter((sample) => !sample.received_at)) {
      await api.post(`/orders/samples/${sample.id}/receive`)
    }
    toast.success(`Orden ${number} recibida: pasa a validación de resultados.`)
    currentId.value = null
    await load()
  } catch (caughtError) {
    toast.error(leoErrorMessage(caughtError))
    await load()
  } finally {
    busyAll.value = false
  }
}
</script>
