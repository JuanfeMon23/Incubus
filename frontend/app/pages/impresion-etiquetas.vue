<template>
  <div class="grid gap-6 lg:grid-cols-[20rem_1fr]">
    <aside>
      <h2 class="mb-2 font-semibold">En espera de impresión ({{ entries.length }})</h2>
      <ul class="space-y-3">
        <li v-for="e in entries" :key="e.id">
          <QueueEntryCard :entry="e" selectable :selected="current?.id === e.id" @select="select(e)" />
        </li>
        <li v-if="listLoading" class="flex justify-center py-4">
          <UiSpinner color="primary" label="Cargando cola" />
        </li>
        <li v-else-if="!entries.length" class="rounded-xl border border-dashed border-border-strong p-8 text-center text-sm text-text-muted">
          Sin órdenes pendientes de impresión.
        </li>
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

        <UiSection
          title="Tubos y etiquetas"
          description="Una etiqueta por tubo, en orden de extracción."
        >
          <div v-if="loading" class="flex justify-center py-8">
            <UiSpinner size="lg" color="primary" label="Preparando tubos" />
          </div>
          <ul v-else class="space-y-3">
            <li v-for="s in order?.samples ?? []" :key="s.id">
              <SampleTubeCard :sample="s">
                <LabelPreview
                  class="mt-1"
                  :patient-name="fullName(current.patient)"
                  :document="`${current.patient.document_type} ${current.patient.document_number}`"
                  :order-number="current.order_number ?? ''"
                  :tube-name="s.name"
                  :area-route="s.area_route"
                />
              </SampleTubeCard>
            </li>
          </ul>
        </UiSection>

        <UiFormField v-if="canPrint" label="Profesional de toma de muestras" required>
          <UiSelect
            v-model="professionalId"
            :options="staffOptions"
            placeholder="Seleccione al profesional…"
            required
          />
        </UiFormField>

        <UiAlert v-if="error" variant="danger" :message="error" />

        <div v-if="canPrint" class="flex flex-wrap justify-end gap-2">
          <UiButton variant="secondary" :disabled="!order?.samples.length" @click="downloadZpl">
            Descargar ZPL
          </UiButton>
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

// Pantalla: label-printing.view. Sin print se ven las órdenes y sus tubos, pero no se imprime ni asigna.
definePageMeta({ leo: { tag: TAGS.labelPrinting.view } })
const canPrint = useCan(TAGS.labelPrinting.print)
const api = useApi()
const toast = useToast()
const labelFiles = useLabelFiles()
const { entries, loading: listLoading, refresh } = useQueueList(['en_espera_impresion'])

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

// La API ya devuelve solo profesionales de toma de muestras.
async function loadStaff() {
  try {
    staff.value = await api<StaffMember[]>('/catalog/staff')
  } catch (e) {
    error.value = apiErrorMessage(e)
    toast.error(error.value)
  }
}

onMounted(loadStaff)

/** Descarga el ZPL (203 dpi, 70x35 mm) para la impresora térmica, con petición firmada (DPoP). */
async function downloadZpl() {
  if (!current.value) return
  try {
    await labelFiles.downloadZpl(current.value.id, current.value.order_number)
  } catch (err) {
    toast.error(apiErrorMessage(err))
  }
}

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
    toast.error(error.value)
  } finally {
    loading.value = false
  }
}

async function print() {
  if (!current.value) return
  const entryId = current.value.id
  const orderNumber = current.value.order_number
  const pro = staff.value.find((s) => s.id === professionalId.value)
  if (!pro) return
  busy.value = true
  error.value = ''
  try {
    await api(`/orders/by-entry/${entryId}/print-labels`, {
      method: 'POST',
      body: { professional_id: pro.id, professional_name: pro.name }
    })
    toast.success(`Etiquetas generadas y paciente asignado a ${pro.name}.`)
    // PDF con una etiqueta por tubo, pedido con petición firmada. Si falla, la
    // asignación ya quedó hecha: se avisa aparte y se puede descargar el ZPL.
    try {
      await labelFiles.openPdf(entryId, orderNumber)
    } catch (pdfErr) {
      toast.error(`Las etiquetas se generaron, pero no se pudo abrir el PDF: ${apiErrorMessage(pdfErr)}`)
    }
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
</script>
