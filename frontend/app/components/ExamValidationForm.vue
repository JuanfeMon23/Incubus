<template>
  <div>
    <div v-if="loading" class="space-y-4" aria-busy="true" aria-label="Cargando plantilla">
      <div class="h-14 animate-pulse rounded-lg bg-default-100" />
      <div v-for="placeholderIndex in 4" :key="placeholderIndex" class="h-24 animate-pulse rounded-xl bg-default-100" />
    </div>

    <div v-else-if="detail" class="space-y-5">
      <p class="text-right text-xs text-text-muted">{{ savingLabel }}</p>

      <section v-for="group in groups" :key="group.name" class="space-y-3">
        <h3 class="text-sm font-semibold uppercase tracking-wide text-text-muted">{{ group.name }}</h3>
        <div
          v-for="row in group.rows"
          :key="row.code"
          class="relative overflow-hidden rounded-xl border bg-surface p-4 pl-5 shadow-sm transition-colors"
          :class="rowClass(row.flag)"
        >
          <span class="absolute inset-y-0 left-0 w-1.5" :class="stripeClass(row.flag)" aria-hidden="true" />
          <div class="grid items-start gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,17rem)]">
            <!-- Analito y referencia -->
            <div class="space-y-2">
              <div class="flex flex-wrap items-center gap-2">
                <p class="font-semibold leading-tight">
                  {{ row.name }}
                  <span v-if="row.is_required && row.result_type !== 'calculated'" class="text-danger-600" aria-hidden="true">*</span>
                </p>
                <UiStatusBadge v-if="row.result_type === 'calculated'" variant="primary" label="Calculado" />
                <UiStatusBadge
                  v-if="flagBadge(row.flag)"
                  :variant="flagBadge(row.flag)!.variant"
                  :label="flagBadge(row.flag)!.label"
                  dot
                />
              </div>

              <div v-if="row.reference || row.unit" class="flex flex-wrap items-center gap-2 text-xs">
                <span
                  v-if="row.reference"
                  class="inline-flex items-center gap-1 rounded-md bg-success-50 px-2 py-1 font-medium text-success-700"
                >
                  <svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="m5 12 4.5 4.5L19 7" />
                  </svg>
                  Normal: {{ row.reference }}<template v-if="row.unit"> {{ row.unit }}</template>
                </span>
                <span
                  v-if="row.range && (row.range.critical_low !== null || row.range.critical_high !== null)"
                  class="rounded-md bg-danger-50 px-2 py-1 font-medium text-danger-700"
                >
                  Crítico:
                  <template v-if="row.range.critical_low !== null">&lt; {{ row.range.critical_low }}</template>
                  <template v-if="row.range.critical_low !== null && row.range.critical_high !== null"> o </template>
                  <template v-if="row.range.critical_high !== null">&gt; {{ row.range.critical_high }}</template>
                </span>
              </div>

              <p v-if="enteredBy(row)" class="text-xs text-text-muted">{{ enteredBy(row) }}</p>

              <RangeBar
                v-if="row.range && typeof numericValue(row) === 'number' || (row.range && row.value === null)"
                class="max-w-xs"
                :range="row.range"
                :value="numericValue(row)"
                :flag="row.flag"
              />
            </div>

            <!-- Captura -->
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <div class="min-w-0 flex-1">
                  <p v-if="!canWork" class="text-sm font-medium" data-testid="result-value">{{ displayValue(row) }}</p>
                  <UiSelect
                    v-else-if="isOption(row)"
                    :model-value="String(form[row.code] ?? '')"
                    :options="row.options.map((option) => ({ value: option.id, label: option.label }))"
                    placeholder="Seleccione…"
                    :disabled="validated"
                    @update:model-value="setValue(row.code, $event)"
                  />
                  <UiSelect
                    v-else-if="row.result_type === 'boolean'"
                    :model-value="boolText(form[row.code])"
                    :options="[{ value: 'true', label: 'Sí / Positivo' }, { value: 'false', label: 'No / Negativo' }]"
                    placeholder="Seleccione…"
                    :disabled="validated"
                    @update:model-value="setValue(row.code, $event)"
                  />
                  <UiTextarea
                    v-else-if="row.result_type === 'text'"
                    :model-value="String(form[row.code] ?? '')"
                    :rows="2"
                    :disabled="validated"
                    @update:model-value="setValue(row.code, $event)"
                  />
                  <UiTextInput
                    v-else
                    :model-value="String(form[row.code] ?? '')"
                    :disabled="validated || row.result_type === 'calculated'"
                    inputmode="decimal"
                    :placeholder="row.result_type === 'calculated' ? 'Automático' : 'Resultado'"
                    @update:model-value="setValue(row.code, $event)"
                  />
                </div>
                <span v-if="row.unit" class="shrink-0 text-sm font-medium text-text-muted">{{ row.unit }}</span>
              </div>
              <p v-if="errors[row.code]" class="text-xs text-danger-600">{{ errors[row.code] }}</p>
            </div>
          </div>
        </div>
      </section>

      <UiAlert v-if="error" variant="danger" :message="error" />
    </div>


    <UiAlert v-if="detail && !canWork" variant="info" class="mt-4">
      Solo lectura: no tienes permiso para «{{ enterName }}» ni «{{ validateName }}».
    </UiAlert>

    <div v-if="detail && (validation.professional || validation.executor)" class="mt-4 space-y-0.5 text-sm text-text-muted">
      <p v-if="validation.professional">{{ validation.professional }}</p>
      <p v-if="validation.executor">{{ validation.executor }}</p>
    </div>

    <div v-if="detail && canWork" class="mt-5 flex flex-wrap justify-end gap-2 border-t border-border pt-4">
      <UiButton v-if="canEnter" variant="secondary" :loading="saving" :disabled="validated || finishing" @click="saveNow">
        Guardar borrador
      </UiButton>
      <UiButton v-if="canValidate" :loading="finishing" :disabled="validated || loading" @click="finish">
        Finalizar validación de {{ detail.name }}
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ResultRow, ResultTestDetail } from '../types'
import { enteredByLabel, validationLabels } from '../utils/resultAuthorship'

const props = defineProps<{
  orderTestId: string
  professionalId: string
  professionalName: string
}>()
const emit = defineEmits<{
  validated: [payload: { orderFinalized: boolean; name: string; orderTestId: string }]
}>()

const api = useLeoAppApi()
const user = useLeoUser()
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

// results.enter guarda borradores; results.validate valida (y envía los valores). Sin ninguno, solo lectura.
const canEnter = useCan(TAGS.results.enter)
const canValidate = useCan(TAGS.results.validate)
const canWork = computed(() => canEnter.value || canValidate.value)
const enterName = permissionName(TAGS.results.enter)
const validateName = permissionName(TAGS.results.validate)
// Validado (negocio): controles deshabilitados. Sin permiso: el valor se muestra como texto, sin controles.
const validated = computed(() => detail.value?.validation_status === 'validated')
const savingLabel = computed(() => {
  if (saving.value) return 'Guardando borrador…'
  if (dirty.value) return 'Cambios sin guardar'
  return lastSaved.value ? `Borrador guardado ${lastSaved.value.toLocaleTimeString()}` : ''
})

const enteredBy = (row: ResultRow) => enteredByLabel(row, user.value?.id)
const validation = computed(() =>
  detail.value ? validationLabels(detail.value, user.value?.id) : { professional: null, executor: null }
)

const groups = computed(() => {
  const map = new Map<string, ResultRow[]>()
  for (const result of detail.value?.results ?? []) {
    const key = result.section || detail.value?.name || 'Resultados'
    map.set(key, [...(map.get(key) ?? []), result])
  }
  return [...map.entries()].map(([name, rows]) => ({ name, rows }))
})

const isOption = (row: ResultRow) =>
  ['qualitative', 'semi_quantitative', 'titer'].includes(row.result_type)
function displayValue(row: ResultRow) {
  const value = form[row.code]
  if (value === null || value === undefined || value === '') return '—'
  if (isOption(row)) return row.options.find((option) => option.id === String(value))?.label ?? String(value)
  if (row.result_type === 'boolean') return value === true || value === 'true' ? 'Sí / Positivo' : 'No / Negativo'
  return String(value)
}
const boolText = (value: unknown) => (value === true ? 'true' : value === false ? 'false' : '')

function isCritical(flag: string | null) {
  return flag === 'critical_low' || flag === 'critical_high'
}
function isAbnormal(flag: string | null) {
  return flag === 'low' || flag === 'high' || flag === 'abnormal'
}
function rowClass(flag: string | null) {
  if (isCritical(flag)) return 'border-danger-300 bg-danger-50/60'
  if (isAbnormal(flag)) return 'border-warning-300 bg-warning-50/60'
  return 'border-border'
}
function stripeClass(flag: string | null) {
  if (isCritical(flag)) return 'bg-danger-500'
  if (isAbnormal(flag)) return 'bg-warning-500'
  if (flag === 'normal') return 'bg-success-500'
  return 'bg-default-200'
}
function numericValue(row: ResultRow): number | null {
  const raw = form[row.code] ?? row.value
  const numeric = typeof raw === 'number' ? raw : Number(String(raw ?? '').replace(',', '.'))
  return raw === null || raw === '' || Number.isNaN(numeric) ? null : numeric
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

function hydrate(loadedDetail: ResultTestDetail) {
  detail.value = loadedDetail
  for (const result of loadedDetail.results) form[result.code] = result.value
}

const query = computed(() => ({ professional_id: props.professionalId }))

onMounted(async () => {
  try {
    hydrate(await api.get<ResultTestDetail>(`/results/tests/${props.orderTestId}`, { query: query.value }))
  } catch (caughtError) {
    error.value = leoErrorMessage(caughtError)
    toast.error(error.value)
  } finally {
    loading.value = false
  }
})

/** Valores digitables (los calculados los obtiene el servidor). */
function payloadValues() {
  const out: Record<string, string | boolean | number | null> = {}
  for (const result of detail.value?.results ?? []) {
    if (result.result_type === 'calculated') continue
    const value = form[result.code]
    out[result.code] = value === undefined || value === '' ? null : value
  }
  return out
}

function applyServerErrors(caughtError: unknown) {
  const data = (caughtError as { data?: { details?: { field?: string; codes?: string[] }; message?: string } })?.data
  const field = data?.details?.field
  Object.keys(errors).forEach((key) => delete errors[key])
  if (field) errors[field] = leoErrorMessage(caughtError)
  for (const code of data?.details?.codes ?? []) errors[code] = 'Este resultado es obligatorio.'
}

async function save(silent = true) {
  if (validated.value || !canWork.value || !detail.value) return true
  saving.value = true
  try {
    const res = await api.put<ResultTestDetail>(`/results/tests/${props.orderTestId}/values`, {
        professional_id: props.professionalId,
        professional_name: props.professionalName,
        values: payloadValues()
      })
    hydrate(res)
    Object.keys(errors).forEach((key) => delete errors[key])
    dirty.value = false
    lastSaved.value = new Date()
    error.value = ''
    return true
  } catch (caughtError) {
    applyServerErrors(caughtError)
    if (!silent) toast.error(leoErrorMessage(caughtError))
    error.value = leoErrorMessage(caughtError)
    return false
  } finally {
    saving.value = false
  }
}

let timer: ReturnType<typeof setTimeout> | undefined
function setValue(code: string, value: unknown) {
  const row = detail.value?.results.find((result) => result.code === code)
  form[code] = row?.result_type === 'boolean' && value !== '' ? value === 'true' : (value as string)
  dirty.value = true
  clearTimeout(timer)
  // El borrador automático exige `enter`; con solo `validate` los valores viajan al validar.
  if (canEnter.value) timer = setTimeout(() => void save(true), 900)
}

async function saveNow() {
  clearTimeout(timer)
  if (await save(false)) toast.success('Borrador guardado.')
}

/** El modal padre lo llama al cerrar: el borrador se conserva. */
async function flush() {
  clearTimeout(timer)
  if (dirty.value && canEnter.value) await save(true)
}
defineExpose({ flush })

async function finish() {
  clearTimeout(timer)
  finishing.value = true
  error.value = ''
  try {
    const res = await api.post<ResultTestDetail & { order_finalized: boolean }>(`/results/tests/${props.orderTestId}/validate`, {
          professional_id: props.professionalId,
          professional_name: props.professionalName,
          values: payloadValues()
        })
    toast.success(
      res.order_finalized
        ? `Examen validado. La orden ${res.order_number} quedó finalizada.`
        : `Examen ${res.name} validado.`
    )
    emit('validated', {
      orderFinalized: res.order_finalized,
      name: res.name,
      orderTestId: props.orderTestId
    })
  } catch (caughtError) {
    applyServerErrors(caughtError)
    error.value = leoErrorMessage(caughtError)
    toast.error(error.value)
  } finally {
    finishing.value = false
  }
}

onBeforeUnmount(() => clearTimeout(timer))
</script>
