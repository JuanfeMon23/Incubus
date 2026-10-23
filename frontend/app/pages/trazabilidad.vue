<template>
  <div class="space-y-5">
    <UiPageHeader
      title="Trazabilidad"
      description="Línea de tiempo de una prueba: quién hizo qué y cuándo, desde el ingreso a la cola hasta la entrega."
    />

    <UiCard>
      <form class="flex flex-wrap items-end gap-3" @submit.prevent="search()">
        <UiFormField label="Número de orden" class="w-full sm:w-72">
          <UiTextInput v-model="orderInput" placeholder="Número de orden" />
        </UiFormField>
        <UiButton type="submit" :loading="searching" :disabled="!orderInput.trim()">Buscar</UiButton>
      </form>
    </UiCard>

    <UiAlert v-if="error" variant="danger" :message="error" />
    <div v-if="searching" class="flex justify-center py-6">
      <UiSpinner color="primary" label="Buscando la orden" />
    </div>

    <UiCard v-else-if="searched && tests.length">
      <h2 class="mb-2 text-sm font-semibold">Pruebas de la orden <span class="font-mono">{{ searched }}</span></h2>
      <ul class="flex flex-wrap gap-2" aria-label="Pruebas de la orden">
        <li v-for="t in tests" :key="t.id">
          <UiButton
            size="sm"
            :variant="t.id === testId ? 'primary' : 'secondary'"
            :aria-pressed="t.id === testId"
            @click="selectTest(t.id)"
          >{{ t.code }} · {{ t.name }}</UiButton>
        </li>
      </ul>
    </UiCard>
    <p
      v-else-if="searched && !error"
      class="rounded-xl border border-dashed border-border-strong p-8 text-center text-sm text-text-muted"
    >
      La orden no tiene pruebas para mostrar.
    </p>
    <p
      v-else-if="!searched && !error"
      class="rounded-xl border border-dashed border-border-strong p-8 text-center text-sm text-text-muted"
    >
      Busque una orden por su número para ver la trazabilidad de sus pruebas.
    </p>

    <UiCard v-if="searched && testId">
      <TraceView :order-number="searched" :test-id="testId" />
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import { TAGS } from '../utils/tags'

// Pantalla: results.trace. También se abre desde Resultados: /trazabilidad?orden=..&prueba=..
definePageMeta({ leo: { tag: TAGS.results.trace } })

interface TraceTest { id: string; code: string; name: string }

const api = useLeoAppApi()
const route = useRoute()
const router = useRouter()

const orderInput = ref('')
const searched = ref('')
const tests = ref<TraceTest[]>([])
const testId = ref('')
const searching = ref(false)
const error = ref('')

const one = (v: unknown) => (Array.isArray(v) ? String(v[0] ?? '') : v ? String(v) : '')

async function search(preferredTest = '') {
  const number = orderInput.value.trim()
  if (!number) return
  searching.value = true
  error.value = ''
  tests.value = []
  testId.value = ''
  searched.value = ''
  try {
    const res = await api.get<{ tests: TraceTest[] }>(`/orders/${encodeURIComponent(number)}/tests`)
    searched.value = number
    tests.value = res.tests
    const chosen = tests.value.find((t) => t.id === preferredTest) ?? (tests.value.length === 1 ? tests.value[0] : undefined)
    if (chosen) selectTest(chosen.id)
  } catch (e) {
    error.value = leoErrorMessage(e)
  } finally {
    searching.value = false
  }
}

function selectTest(id: string) {
  testId.value = id
  void router.replace({ query: { orden: searched.value, prueba: id } })
}

onMounted(async () => {
  const orden = one(route.query.orden)
  if (orden) {
    orderInput.value = orden
    await search(one(route.query.prueba))
  }
})
</script>
