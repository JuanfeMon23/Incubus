<template>
  <UiModal :open="true" size="md" title="Comprobante de recepción" @close="emit('close')">
    <div class="activation-receipt space-y-4 text-center">
      <p class="text-sm text-text-muted">Orden</p>
      <p class="font-mono text-2xl font-bold" data-testid="receipt-order">{{ orderNumber }}</p>

      <div class="rounded-xl border-2 border-dashed border-border-strong p-4">
        <p class="text-sm font-medium">
          Código de activación de Acuarius (portal de pacientes para ver sus resultados)
        </p>
        <p
          class="my-3 select-all font-mono text-4xl font-bold tracking-widest"
          data-testid="receipt-code"
        >{{ activationCode }}</p>
        <p class="text-xs text-text-muted">Vigencia: 30 días.</p>
      </div>

      <UiAlert variant="warning" class="no-print">
        Este código solo se muestra ahora; no se puede recuperar.
      </UiAlert>
      <p class="print-only hidden text-sm font-semibold">Este código solo se muestra una vez; no se puede recuperar.</p>
      <p v-if="copyError" class="no-print text-sm text-danger-700">{{ copyError }}</p>
    </div>
    <template #footer="{ close }">
      <div class="no-print flex w-full justify-end gap-2">
        <UiButton variant="ghost" @click="close">Cerrar</UiButton>
        <UiButton variant="secondary" @click="copy">{{ copied ? 'Copiado' : 'Copiar' }}</UiButton>
        <UiButton @click="print">Imprimir</UiButton>
      </div>
    </template>
  </UiModal>
</template>

<script setup lang="ts">
// El código vive solo en las props de este modal (memoria): sin store, localStorage, logs ni URL.
const props = defineProps<{ orderNumber: string; activationCode: string }>()
const emit = defineEmits<{ close: [] }>()

const copied = ref(false)
const copyError = ref('')

async function copy() {
  copyError.value = ''
  try {
    await navigator.clipboard.writeText(props.activationCode)
    copied.value = true
  } catch {
    copyError.value = 'No se pudo copiar. Selecciona el código y cópialo manualmente.'
  }
}

function print() {
  window.print()
}
</script>

<style>
@media print {
  body * { visibility: hidden !important; }
  .activation-receipt, .activation-receipt * { visibility: visible !important; }
  .activation-receipt { position: fixed; inset: 0; padding: 2rem; background: #fff; color: #000; }
  .activation-receipt .no-print { display: none !important; }
  .activation-receipt .print-only { display: block !important; }
}
</style>
