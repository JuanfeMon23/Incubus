<template>
  <div class="space-y-5">
    <UiCard>
      <div class="grid gap-4 md:grid-cols-[minmax(0,18rem)_1fr]">
        <UiFormField label="Profesional" required>
          <UiSelect
            v-model="professionalId"
            :options="validatorOptions"
            placeholder="Seleccione quién valida…"
          />
        </UiFormField>
        <UiFormField label="Buscar órdenes de mi área">
          <UiTextInput
            v-model="search"
            :disabled="!professionalId"
            placeholder="Orden, documento, paciente o examen…"
          />
        </UiFormField>
      </div>
      <p v-if="professional" class="mt-3 flex flex-wrap items-center gap-2 text-sm text-text-muted">
        Áreas asignadas:
        <span
          v-for="a in professional.areas"
          :key="a.id"
          class="rounded-full bg-secondary-50 px-2 py-0.5 text-xs font-semibold text-secondary-700"
        >{{ a.code }} · {{ a.name }}</span>
      </p>
    </UiCard>

    <div v-if="!professionalId" class="rounded-xl border border-dashed border-border-strong p-10 text-center text-sm text-text-muted">
      Seleccione al profesional para cargar las órdenes de su área.
    </div>
    <div v-else-if="loading" class="flex justify-center py-10">
      <UiSpinner size="lg" color="primary" label="Cargando órdenes" />
    </div>
    <ul v-else class="grid gap-3 md:grid-cols-2">
      <li v-for="o in orders" :key="o.entry_id">
        <UiCard>
          <div class="space-y-3">
            <div>
              <p class="font-semibold">{{ o.patient_name }}</p>
              <p class="text-xs text-text-muted">
                {{ o.document }} · Orden <span class="font-mono">{{ o.order_number }}</span>
              </p>
            </div>
            <ul class="space-y-2">
              <li
                v-for="t in o.tests"
                :key="t.order_test_id"
                class="flex items-center gap-3 rounded-lg bg-default-50 px-3 py-2"
              >
                <span class="rounded-md bg-white px-2 py-0.5 font-mono text-xs font-semibold">{{ t.code }}</span>
                <span class="min-w-0 flex-1 truncate text-sm">{{ t.name }}</span>
                <UiStatusBadge
                  :variant="t.validation_status === 'draft' ? 'warning' : 'neutral'"
                  :label="t.validation_status === 'draft' ? 'Borrador' : 'Pendiente'"
                />
                <UiButton size="sm" @click="openOrder(o.entry_id, t.order_test_id)">{{ canWork ? 'Validar' : 'Ver' }}</UiButton>
              </li>
            </ul>
          </div>
        </UiCard>
      </li>
      <li v-if="!orders.length" class="col-span-full text-sm text-text-muted">
        {{ search ? 'Sin resultados para la búsqueda.' : 'No hay órdenes pendientes de validar en tus áreas.' }}
      </li>
    </ul>

    <ValidationModal
      v-if="openEntry && professional"
      :entry-id="openEntry"
      :focus-test-id="openFocus"
      :professional-id="professional.id"
      :professional-name="professional.name"
      @close="closeModal"
    />
  </div>
</template>

<script setup lang="ts">
import type { ResultsQueueOrder, ValidatorStaff } from '../types'

// Pantalla: results.view. Capturar (enter) y validar (validate) se controlan en cada examen.
definePageMeta({ leo: { tag: TAGS.results.view } })
const canWork = useCan([TAGS.results.enter, TAGS.results.validate], 'any')
const api = useApi()
const toast = useToast()

const validators = ref<ValidatorStaff[]>([])
const validatorOptions = computed(() => validators.value.map((v) => ({ value: v.id, label: v.name })))
const professionalId = ref('')
const professional = computed(() => validators.value.find((v) => v.id === professionalId.value) ?? null)

const orders = ref<ResultsQueueOrder[]>([])
const loading = ref(false)
const search = ref('')
const openEntry = ref<string | null>(null)
const openFocus = ref<string | null>(null)

onMounted(async () => {
  try {
    validators.value = await api<ValidatorStaff[]>('/catalog/validators')
    const saved = localStorage.getItem('incubus.validator') ?? ''
    if (validators.value.some((v) => v.id === saved)) professionalId.value = saved
  } catch (e) {
    toast.error(apiErrorMessage(e))
  }
})

async function load() {
  if (!professionalId.value) {
    orders.value = []
    return
  }
  loading.value = true
  try {
    orders.value = await api<ResultsQueueOrder[]>('/results/queue', {
      query: { professional_id: professionalId.value, ...(search.value.trim() ? { q: search.value.trim() } : {}) }
    })
  } catch (e) {
    toast.error(apiErrorMessage(e))
  } finally {
    loading.value = false
  }
}

watch(professionalId, (id) => {
  try {
    localStorage.setItem('incubus.validator', id)
  } catch {
    /* almacenamiento no disponible */
  }
  void load()
})
// No recarga la cola mientras se valida (closeModal la recarga).
useQueueRefresh(['en_laboratorio'], load, { enabled: () => !openEntry.value })
let timer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
})

function openOrder(entryId: string, testId: string) {
  openEntry.value = entryId
  openFocus.value = testId
}

async function closeModal() {
  openEntry.value = null
  openFocus.value = null
  await load()
}
</script>
