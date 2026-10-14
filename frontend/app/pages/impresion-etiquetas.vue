<template>
  <div class="grid gap-6 lg:grid-cols-[20rem_1fr]">
    <aside>
      <h2 class="mb-2 font-semibold">En espera de impresión ({{ entries.length }})</h2>
      <ul class="space-y-2">
        <li v-for="e in entries" :key="e.id">
          <button
            type="button"
            class="w-full rounded-lg border-2 bg-surface p-3 text-left text-sm shadow-sm transition-colors"
            :class="current?.id === e.id ? 'border-primary-500' : 'border-transparent'"
            :style="{ borderLeft: `6px solid ${e.priority.color_hex}` }"
            @click="select(e)"
          >
            <span class="block truncate font-medium">{{ fullName(e.patient) }}</span>
            <span class="text-xs text-text-muted">
              Orden {{ e.order_number }} · {{ waitingLabel(e.arrived_at) }}
            </span>
          </button>
        </li>
        <li v-if="!entries.length" class="text-sm text-text-muted">Sin órdenes pendientes de impresión.</li>
      </ul>
    </aside>

    <UiCard v-if="current">
      <div class="space-y-5">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h1 class="text-lg font-semibold">{{ fullName(current.patient) }}</h1>
            <p class="text-sm text-text-muted">
              {{ current.patient.document_type }} {{ current.patient.document_number }} ·
              Orden <span class="font-mono">{{ current.order_number }}</span>
            </p>
          </div>
          <PriorityBadge :priority="current.priority" />
        </div>

        <UiSection title="Tubos y etiquetas" description="Una etiqueta por tubo, en orden de extracción.">
          <p v-if="loading" class="text-sm text-text-muted">Preparando tubos…</p>
          <ul v-else class="space-y-2">
            <li
              v-for="s in order?.samples ?? []"
              :key="s.id"
              class="flex items-center gap-3 rounded-lg border border-border p-3"
            >
              <span
                class="h-5 w-5 shrink-0 rounded-full border border-border-strong"
                :style="{ backgroundColor: s.cap_color_hex || '#e4e4e7' }"
              />
              <div class="min-w-0 flex-1">
                <p class="font-medium">
                  {{ s.name }}
                  <span v-if="formatVolume(s.required_volume_ml)" class="text-sm font-normal text-text-muted">
                    · {{ formatVolume(s.required_volume_ml) }}
                  </span>
                </p>
                <p class="text-xs text-text-muted">
                  Exámenes: {{ s.test_codes.join(', ') }} · Ruta: {{ s.area_route.join(' > ') || '—' }}
                </p>
              </div>
            </li>
          </ul>
        </UiSection>

        <UiFormField label="Profesional de toma de muestras" required>
          <UiSelect
            v-model="professionalId"
            :options="staffOptions"
            placeholder="Seleccione al profesional…"
            required
          />
        </UiFormField>

        <UiAlert v-if="error" variant="danger" :message="error" />

        <div class="flex justify-end">
          <UiButton :disabled="!professionalId || !order?.samples.length" :loading="busy" @click="print">
            Imprimir etiquetas y asignar
          </UiButton>
        </div>
      </div>
    </UiCard>
    <UiCard v-else>
      <p class="py-10 text-center text-sm text-text-muted">
        Seleccione una orden para ver sus tubos, imprimir etiquetas y asignar al profesional.
      </p>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import type { OrderDetail, QueueEntry, StaffMember } from '../types'

const ACTOR = 'impresion'
const api = useApi()
const apiBase = useRuntimeConfig().public.apiBase
const { entries, refresh } = useQueueList(['en_espera_impresion'])

const staff = ref<StaffMember[]>([])
const staffOptions = computed(() =>
  staff.value.map((s) => ({ value: s.id, label: s.job_title ? `${s.name} · ${s.job_title}` : s.name }))
)
const professionalId = ref('')
const currentId = ref<string | null>(null)
const current = computed(() => entries.value.find((e) => e.id === currentId.value) ?? null)
const order = ref<OrderDetail | null>(null)
const loading = ref(false)
const busy = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    staff.value = await api<StaffMember[]>('/catalog/staff')
  } catch (e) {
    error.value = apiErrorMessage(e)
  }
})

async function select(e: QueueEntry) {
  currentId.value = e.id
  error.value = ''
  order.value = null
  professionalId.value = ''
  loading.value = true
  try {
    order.value = await api<OrderDetail>(`/orders/by-entry/${e.id}/samples`, { method: 'POST' })
  } catch (err) {
    error.value = apiErrorMessage(err)
  } finally {
    loading.value = false
  }
}

async function print() {
  if (!current.value) return
  const entryId = current.value.id
  const pro = staff.value.find((s) => s.id === professionalId.value)
  if (!pro) return
  busy.value = true
  error.value = ''
  try {
    await api(`/orders/by-entry/${entryId}/print-labels`, {
      method: 'POST',
      body: { professional_id: pro.id, professional_name: pro.name, actor: ACTOR }
    })
    // PDF básico con una etiqueta por tubo; ZPL para impresora térmica queda como mejora.
    window.open(`${apiBase}/orders/by-entry/${entryId}/labels.pdf`, '_blank')
    currentId.value = null
    order.value = null
    await refresh()
  } catch (err) {
    error.value = apiErrorMessage(err)
  } finally {
    busy.value = false
  }
}
</script>
