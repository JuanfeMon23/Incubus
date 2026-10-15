<template>
  <UiModal
    :open="true"
    :dismissable="false"
    hide-close-button
    size="xl"
    :title="detail ? `${detail.name} · Orden ${detail.order_number}` : 'Validación de resultados'"
  >
    <div v-if="loading" class="flex justify-center py-16">
      <UiSpinner size="lg" color="primary" label="Cargando plantilla" />
    </div>

    <div v-else-if="detail" class="space-y-5">
      <header class="flex flex-wrap items-center gap-x-6 gap-y-1 rounded-lg bg-default-100 px-4 py-3 text-sm">
        <span class="font-semibold">{{ detail.patient.name }}</span>
        <span>{{ detail.patient.document_type }} {{ detail.patient.document_number }}</span>
        <span>Sexo: {{ detail.patient.sex ?? '—' }}</span>
        <span>Edad: {{ detail.patient.age_years !== null ? `${Math.floor(detail.patient.age_years)} años` : '—' }}</span>
        <span class="ml-auto text-text-muted">{{ savingLabel }}</span>
      </header>

      <section v-for="group in groups" :key="group.name" class="space-y-3">
        <h3 class="text-sm font-semibold uppercase tracking-wide text-text-muted">{{ group.name }}</h3>
        <div
          v-for="r in group.rows"
          :key="r.code"
          class="grid items-start gap-3 rounded-lg border border-border p-3 sm:grid-cols-[minmax(0,1fr)_14rem_9rem]"
          :class="flagRow(r.flag)"
        >
          <div>
            <p class="font-medium">
              {{ r.name }}
              <span v-if="r.is_required && r.result_type !== 'calculated'" class="text-danger-600" aria-hidden="true">*</span>
            </p>
            <p class="text-xs text-text-muted">
              <template v-if="r.reference">Referencia: {{ r.reference }}</template>
              <template v-if="r.result_type === 'calculated'"> · calculado</template>
            </p>
          </div>

          <div class="space-y-1">
            <UiSelect
              v-if="isOption(r)"
              :model-value="String(form[r.code] ?? '')"
              :options="r.options.map((o) => ({ value: o.id, label: o.label }))"
              placeholder="Seleccione…"
              :disabled="readonly"
              @update:model-value="setValue(r.code, $event)"
            />
            <UiSelect
              v-else-if="r.result_type === 'boolean'"
              :model-value="boolText(form[r.code])"
              :options="[{ value: 'true', label: 'Sí / Positivo' }, { value: 'false', label: 'No / Negativo' }]"
              placeholder="Seleccione…"
              :disabled="readonly"
              @update:model-value="setValue(r.code, $event)"
            />
            <UiTextarea
              v-else-if="r.result_type === 'text'"
              :model-value="String(form[r.code] ?? '')"
              :rows="2"
              :disabled="readonly"
              @update:model-value="setValue(r.code, $event)"
            />
            <UiTextInput
              v-else
              :model-value="String(form[r.code] ?? '')"
              :disabled="readonly || r.result_type === 'calculated'"
              inputmode="decimal"
              :placeholder="r.result_type === 'calculated' ? 'Automático' : 'Resultado'"
              @update:model-value="setValue(r.code, $event)"
            />
            <p v-if="errors[r.code]" class="text-xs text-danger-600">{{ errors[r.code] }}</p>
          </div>

          <div class="flex items-center gap-2 pt-1 text-sm">
            <span v-if="r.unit" class="text-text-muted">{{ r.unit }}</span>
            <UiStatusBadge v-if="flagBadge(r.flag)" :variant="flagBadge(r.flag)!.variant" :label="flagBadge(r.flag)!.label" dot />
          </div>
        </div>
      </section>

      <UiAlert v-if="error" variant="danger" :message="error" />
    </div>

    <template #footer>
      <div class="flex w-full flex-wrap items-center justify-between gap-2">
        <UiButton variant="secondary" :disabled="finishing" @click="closeModal">Cerrar</UiButton>
        <div class="flex gap-2">
          <UiButton variant="secondary" :loading="saving" :disabled="readonly || finishing" @click="saveNow">
            Guardar borrador
          </UiButton>
          <UiButton :loading="finishing" :disabled="readonly || loading" @click="finish">
            Finalizar validación
          </UiButton>
        </div>
      </div>
    </template>
  </UiModal>
</template>

<script setup lang="ts">
import type { ResultRow, ResultTestDetail } from '../types'

const props = defineProps<{
  orderTestId: string
  professionalId: string
  professionalName: string
}>()
const emit = defineEmits<{
  close: []
  validated: [payload: { orderFinalized: boolean; name: string }]
}>()

const api = useApi()
const toast = useToast()

const detail = ref<ResultTestDetail | null>(null)
const loading = ref(true)
const saving = ref(false)
const finishing = ref(false)
const error = ref('')
const errors = reactive<Record<string, string>>({})
const form = reactive<Record<string, string | number | boolean | null>>({})
const dirty = ref(false)
const lastSaved = ref<Date | null>(null)

const readonly = computed(() => detail.value?.validation_status === 'validated')
const savingLabel = computed(() => {
  if (saving.value) return 'Guardando borrador…'
  if (dirty.value) return 'Cambios sin guardar'
  return lastSaved.value ? `Borrador guardado ${lastSaved.value.toLocaleTimeString()}` : ''
})

const groups = computed(() => {
  const map = new Map<string, ResultRow[]>()
  for (const r of detail.value?.results ?? []) {
    const key = r.section || detail.value?.name || 'Resultados'
    map.set(key, [...(map.get(key) ?? []), r])
  }
  return [...map.entries()].map(([name, rows]) => ({ name, rows }))
})

const isOption = (r: ResultRow) =>
  ['qualitative', 'semi_quantitative', 'titer'].includes(r.result_type)
const boolText = (v: unknown) => (v === true ? 'true' : v === false ? 'false' : '')

function flagRow(flag: string | null) {
  if (flag === 'critical_low' || flag === 'critical_high') return 'border-danger-300 bg-danger-50'
  if (flag === 'low' || flag === 'high' || flag === 'abnormal') return 'border-warning-300 bg-warning-50'
  return ''
}

function flagBadge(flag: string | null): { variant: 'success' | 'warning' | 'danger'; label: string } | null {
  switch (flag) {
    case 'normal': return { variant: 'success', label: 'Normal' }
    case 'low': return { variant: 'warning', label: 'Bajo' }
    case 'high': return { variant: 'warning', label: 'Alto' }
    case 'abnormal': return { variant: 'warning', label: 'Anormal' }
    case 'critical_low': return { variant: 'danger', label: 'Crítico bajo' }
    case 'critical_high': return { variant: 'danger', label: 'Crítico alto' }
    default: return null
  }
}

function hydrate(d: ResultTestDetail) {
  detail.value = d
  for (const r of d.results) form[r.code] = r.value
}

const query = computed(() => ({ professional_id: props.professionalId }))

onMounted(async () => {
  try {
    hydrate(await api<ResultTestDetail>(`/results/tests/${props.orderTestId}`, { query: query.value }))
  } catch (e) {
    error.value = apiErrorMessage(e)
    toast.error(error.value)
  } finally {
    loading.value = false
  }
})

/** Valores digitables (los calculados los obtiene el servidor). */
function payloadValues() {
  const out: Record<string, string | boolean | number | null> = {}
  for (const r of detail.value?.results ?? []) {
    if (r.result_type === 'calculated') continue
    const v = form[r.code]
    out[r.code] = v === undefined || v === '' ? null : v
  }
  return out
}

function applyServerErrors(e: unknown) {
  const data = (e as { data?: { details?: { field?: string; codes?: string[] }; message?: string } })?.data
  const field = data?.details?.field
  Object.keys(errors).forEach((k) => delete errors[k])
  if (field) errors[field] = apiErrorMessage(e)
  for (const code of data?.details?.codes ?? []) errors[code] = 'Este resultado es obligatorio.'
}

async function save(silent = true) {
  if (readonly.value || !detail.value) return true
  saving.value = true
  try {
    const res = await api<ResultTestDetail>(`/results/tests/${props.orderTestId}/values`, {
      method: 'PUT',
      body: {
        professional_id: props.professionalId,
        professional_name: props.professionalName,
        values: payloadValues()
      }
    })
    hydrate(res)
    Object.keys(errors).forEach((k) => delete errors[k])
    dirty.value = false
    lastSaved.value = new Date()
    error.value = ''
    return true
  } catch (e) {
    applyServerErrors(e)
    if (!silent) toast.error(apiErrorMessage(e))
    error.value = apiErrorMessage(e)
    return false
  } finally {
    saving.value = false
  }
}

let timer: ReturnType<typeof setTimeout> | undefined
function setValue(code: string, value: unknown) {
  const row = detail.value?.results.find((r) => r.code === code)
  form[code] = row?.result_type === 'boolean' && value !== '' ? value === 'true' : (value as string)
  dirty.value = true
  clearTimeout(timer)
  timer = setTimeout(() => void save(true), 900)
}

async function saveNow() {
  clearTimeout(timer)
  if (await save(false)) toast.success('Borrador guardado.')
}

async function closeModal() {
  clearTimeout(timer)
  if (dirty.value) await save(true) // el borrador se conserva al cerrar
  emit('close')
}

async function finish() {
  clearTimeout(timer)
  finishing.value = true
  error.value = ''
  try {
    const res = await api<ResultTestDetail & { order_finalized: boolean }>(
      `/results/tests/${props.orderTestId}/validate`,
      {
        method: 'POST',
        body: {
          professional_id: props.professionalId,
          professional_name: props.professionalName,
          values: payloadValues()
        }
      }
    )
    toast.success(
      res.order_finalized
        ? `Examen validado. La orden ${res.order_number} quedó finalizada.`
        : `Examen ${res.name} validado.`
    )
    emit('validated', { orderFinalized: res.order_finalized, name: res.name })
  } catch (e) {
    applyServerErrors(e)
    error.value = apiErrorMessage(e)
    toast.error(error.value)
  } finally {
    finishing.value = false
  }
}

onBeforeUnmount(() => clearTimeout(timer))
</script>
