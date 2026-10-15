<template>
  <UiModal
    :open="true"
    :dismissable="false"
    hide-close-button
    size="xl"
    :title="order ? `Validación · Orden ${order.order_number}` : 'Validación de resultados'"
  >
    <div v-if="loading" class="space-y-4" aria-busy="true" aria-label="Cargando orden">
      <div class="h-14 animate-pulse rounded-lg bg-default-100" />
      <div v-for="n in 2" :key="n" class="h-28 animate-pulse rounded-xl bg-default-100" />
    </div>

    <div v-else-if="order" class="space-y-5">
      <header class="flex flex-wrap items-center gap-x-6 gap-y-1 rounded-lg bg-default-100 px-4 py-3 text-sm">
        <span class="font-semibold">{{ order.patient.name }}</span>
        <span>{{ order.patient.document_type }} {{ order.patient.document_number }}</span>
        <span>Sexo: {{ order.patient.sex ?? '—' }}</span>
        <span>
          Edad:
          {{ order.patient.age_years !== null ? `${Math.floor(order.patient.age_years)} años` : '—' }}
        </span>
        <span class="ml-auto font-medium text-text-muted">
          {{ validatedCount }} de {{ order.tests.length }} exámenes validados
        </span>
      </header>

      <UiAlert v-if="allDone" variant="success" title="Todos los exámenes de tu área están validados">
        Puedes cerrar la ventana.
      </UiAlert>

      <ul class="space-y-3">
        <li v-for="t in order.tests" :key="t.order_test_id">
          <!-- Examen ya validado: card verde, sin la información del examen -->
          <div
            v-if="t.validation_status === 'validated'"
            class="flex items-center gap-4 rounded-xl border-2 border-success-300 bg-success-50 px-4 py-3"
          >
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-success-500 text-white">
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="m5 12.5 4.5 4.5L19 7.5" />
              </svg>
            </span>
            <div class="min-w-0 flex-1">
              <p class="truncate font-semibold text-success-800">
                {{ t.name }}
                <span class="ml-1 rounded bg-white/70 px-1.5 py-0.5 font-mono text-xs">{{ t.code }}</span>
              </p>
              <p class="text-xs text-success-700">
                Validado por {{ t.validated_by || '—' }}<template v-if="t.validated_at"> · {{ timeLabel(t.validated_at) }}</template>
              </p>
            </div>
            <UiStatusBadge variant="success" label="Validado" dot />
          </div>

          <!-- Examen pendiente: card con su formulario -->
          <div
            v-else
            class="overflow-hidden rounded-xl border-2 bg-surface transition-colors"
            :class="isOpen(t.order_test_id) ? 'border-primary-300 shadow-md' : 'border-border'"
          >
            <button
              type="button"
              class="flex w-full items-center gap-3 px-4 py-3 text-left"
              :aria-expanded="isOpen(t.order_test_id)"
              @click="toggle(t.order_test_id)"
            >
              <span class="rounded-md bg-default-100 px-2 py-0.5 font-mono text-xs font-semibold">{{ t.code }}</span>
              <span class="min-w-0 flex-1 truncate font-semibold">{{ t.name }}</span>
              <UiStatusBadge
                :variant="t.validation_status === 'draft' ? 'warning' : 'neutral'"
                :label="t.validation_status === 'draft' ? 'Borrador' : 'Pendiente'"
              />
              <svg
                viewBox="0 0 24 24"
                class="h-4 w-4 shrink-0 text-text-muted transition-transform"
                :class="isOpen(t.order_test_id) ? 'rotate-180' : ''"
                fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            </button>

            <div v-if="mounted.has(t.order_test_id)" v-show="isOpen(t.order_test_id)" class="border-t border-border p-4">
              <ExamValidationForm
                :ref="(el) => setFormRef(t.order_test_id, el)"
                :order-test-id="t.order_test_id"
                :professional-id="professionalId"
                :professional-name="professionalName"
                @validated="onValidated"
              />
            </div>
          </div>
        </li>
      </ul>

      <UiAlert v-if="error" variant="danger" :message="error" />
    </div>

    <UiAlert v-else-if="error" variant="danger" :message="error" />

    <template #footer>
      <div class="flex w-full justify-end">
        <UiButton variant="secondary" :loading="closing" @click="closeModal">Cerrar</UiButton>
      </div>
    </template>
  </UiModal>
</template>

<script setup lang="ts">
import type { OrderValidationView } from '../types'

const props = defineProps<{
  entryId: string
  /** Examen que se abre expandido al entrar (el que se pulsó en la lista). */
  focusTestId?: string | null
  professionalId: string
  professionalName: string
}>()
const emit = defineEmits<{
  close: []
}>()

const api = useApi()
const toast = useToast()

const order = ref<OrderValidationView | null>(null)
const loading = ref(true)
const closing = ref(false)
const error = ref('')
const open = ref<Set<string>>(new Set())
const mounted = ref<Set<string>>(new Set())
const formRefs = new Map<string, { flush: () => Promise<void> } | null>()

const validatedCount = computed(
  () => order.value?.tests.filter((t) => t.validation_status === 'validated').length ?? 0
)
const allDone = computed(
  () => !!order.value && order.value.tests.length > 0 && validatedCount.value === order.value.tests.length
)

const isOpen = (id: string) => open.value.has(id)

function toggle(id: string) {
  const next = new Set(open.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  open.value = next
  mounted.value = new Set([...mounted.value, id])
}

function setFormRef(id: string, el: unknown) {
  formRefs.set(id, (el as { flush: () => Promise<void> } | null) ?? null)
}

function timeLabel(iso: string) {
  return new Date(iso).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })
}

async function load() {
  order.value = await api<OrderValidationView>(`/results/orders/${props.entryId}`, {
    query: { professional_id: props.professionalId }
  })
}

onMounted(async () => {
  try {
    await load()
    const pending = order.value?.tests.filter((t) => t.validation_status !== 'validated') ?? []
    const first =
      pending.find((t) => t.order_test_id === props.focusTestId) ?? pending[0] ?? null
    if (first) {
      open.value = new Set([first.order_test_id])
      mounted.value = new Set([first.order_test_id])
    }
  } catch (e) {
    error.value = apiErrorMessage(e)
    toast.error(error.value)
  } finally {
    loading.value = false
  }
})

/** Un examen quedó validado: su card pasa a verde y se abre el siguiente pendiente. */
async function onValidated(payload: { orderTestId: string }) {
  try {
    await load()
  } catch (e) {
    toast.error(apiErrorMessage(e))
  }
  const next = order.value?.tests.find(
    (t) => t.validation_status !== 'validated' && t.order_test_id !== payload.orderTestId
  )
  const opened = new Set(open.value)
  opened.delete(payload.orderTestId)
  if (next) {
    opened.add(next.order_test_id)
    mounted.value = new Set([...mounted.value, next.order_test_id])
  }
  open.value = opened
}

async function closeModal() {
  closing.value = true
  try {
    // los borradores de los exámenes abiertos se conservan al cerrar
    await Promise.all([...formRefs.values()].map((f) => f?.flush()))
  } finally {
    closing.value = false
  }
  emit('close')
}
</script>
