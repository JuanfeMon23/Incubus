<template>
  <div class="space-y-4">
    <header v-if="test" class="flex flex-wrap items-center gap-2">
      <span class="rounded-md bg-default-100 px-2 py-0.5 font-mono text-xs font-semibold">{{ test.code }}</span>
      <span class="font-semibold">{{ test.name }}</span>
      <span class="text-sm text-text-muted">· Orden <span class="font-mono">{{ orderNumber }}</span></span>
    </header>

    <fieldset class="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg bg-default-50 px-3 py-2">
      <legend class="sr-only">Filtros de la línea de tiempo</legend>
      <span class="text-sm text-text-muted">Ámbito:</span>
      <UiCheckbox
        v-for="s in SCOPES"
        :key="s"
        :model-value="scopes.includes(s)"
        :label="SCOPE_LABELS[s]"
        @update:model-value="toggleScope(s, $event)"
      />
      <UiCheckbox v-model="hideQueue" label="Ocultar pasos de cola" />
    </fieldset>

    <TraceTimeline
      :events="shown"
      :loading="loading"
      :error="error"
      :has-more="hasMore"
      :empty-message="events.length ? 'Ningún evento coincide con los filtros.' : 'Esta prueba aún no tiene eventos registrados.'"
      @load-more="loadMore"
    />
  </div>
</template>

<script setup lang="ts">
import type { TraceEvent, TracePage, TraceScope } from '../types'
import { filterEvents, SCOPE_LABELS, SCOPES } from '../utils/trace'

/** Carga y filtra la trazabilidad de una prueba (`GET /orders/{n}/tests/{id}/trace`). */
const props = defineProps<{ orderNumber: string; testId: string }>()

const PAGE_SIZE = 50
const api = useLeoAppApi()
const events = ref<TraceEvent[]>([])
const test = ref<TracePage['test'] | null>(null)
const page = ref(0)
const total = ref(0)
const loading = ref(false)
const error = ref('')
const scopes = ref<TraceScope[]>([...SCOPES])
const hideQueue = ref(false)

const shown = computed(() => filterEvents(events.value, { scopes: scopes.value, hideQueue: hideQueue.value }))
const hasMore = computed(() => events.value.length < total.value)

function toggleScope(scope: TraceScope, on: boolean) {
  scopes.value = on ? SCOPES.filter((s) => s === scope || scopes.value.includes(s)) : scopes.value.filter((s) => s !== scope)
}

let token = 0
async function fetchPage(next: number) {
  const mine = ++token
  loading.value = true
  error.value = ''
  try {
    const res = await api.get<TracePage>(
      `/orders/${encodeURIComponent(props.orderNumber)}/tests/${encodeURIComponent(props.testId)}/trace`,
      { query: { page: next, page_size: PAGE_SIZE } }
    )
    if (mine !== token) return
    events.value = next === 1 ? res.events : [...events.value, ...res.events]
    test.value = res.test
    total.value = res.total
    page.value = next
  } catch (e) {
    if (mine === token) error.value = pageSizeMessage(e) ?? leoErrorMessage(e)
  } finally {
    if (mine === token) loading.value = false
  }
}

function loadMore() {
  if (!loading.value) void fetchPage(page.value + 1)
}

watch(
  () => [props.orderNumber, props.testId],
  () => {
    events.value = []
    test.value = null
    total.value = 0
    void fetchPage(1)
  },
  { immediate: true }
)
</script>
