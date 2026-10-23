<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <UiListToolbar
        v-model:search="list.search.value"
        search-placeholder="Buscar por código o nombre…"
        :searching="list.loading.value"
      >
        <UiActiveFilter
          :id="`queue-admin-active-${kind}`"
          v-model="list.activeFilter.value"
          active-label="Activos"
          inactive-label="Inactivos"
        />
      </UiListToolbar>
      <LeoCan :tag="TAGS.queueAdmin.create">
        <UiButton @click="openCreate">{{ info.feminine ? 'Nueva' : 'Nuevo' }} {{ info.noun }}</UiButton>
      </LeoCan>
    </div>

    <UiAlert v-if="list.loadError.value" variant="danger" :message="list.loadError.value" />

    <UiDataTable
      :columns="columns"
      :rows="list.rows.value"
      :loading="list.loading.value"
      :page="list.page.value"
      :page-size="list.pageSize.value"
      :total="list.total.value"
      :search-term="list.searchTerm.value"
      empty-message="No hay registros con estos filtros."
      @update:page="list.page.value = $event"
      @clear-search="list.search.value = ''"
    >
      <template #cell-name="{ row }">
        <PriorityBadge v-if="priority && row.color_hex" :priority="{ ...row, color_hex: row.color_hex, rank: row.rank ?? 0 }" />
        <span v-else class="font-medium text-text">{{ row.name }}</span>
      </template>
      <template #cell-code="{ row }">
        <span class="font-mono text-xs text-text-muted">{{ row.code }}</span>
      </template>
      <template #cell-is_active="{ row }">
        <div class="flex flex-wrap items-center gap-1">
          <UiStatusBadge :active="row.is_active" />
          <UiStatusBadge v-if="row.is_default === true" variant="primary" label="Por defecto" />
        </div>
      </template>
      <template #cell-updated_at="{ row }">
        <span class="text-text-muted">{{ formatDateTime(row.updated_at) }}</span>
      </template>
      <template #cell-id="{ row }">
        <div class="flex flex-wrap justify-end gap-1">
          <LeoCan :tag="TAGS.queueAdmin.update">
            <UiButton variant="ghost" size="sm" :aria-label="`Editar ${row.name}`" @click="openEdit(row)">Editar</UiButton>
            <UiButton
              v-if="priority"
              variant="ghost"
              size="sm"
              :disabled="!canMakeDefault(kind, row)"
              :aria-label="`Hacer predeterminada ${row.name}`"
              @click="openSetDefault(row)"
            >Hacer predeterminada</UiButton>
          </LeoCan>
          <LeoCan :tag="TAGS.queueAdmin.toggle">
            <UiButton
              v-if="!row.is_active"
              variant="ghost"
              size="sm"
              :aria-label="`Reactivar ${row.name}`"
              @click="reactivation.ask(row)"
            >Reactivar</UiButton>
            <span v-else :title="blocked(row) ?? undefined" class="inline-flex">
              <UiButton
                variant="danger-ghost"
                size="sm"
                :disabled="blocked(row) !== null"
                :aria-label="`Desactivar ${row.name}`"
                :aria-describedby="blocked(row) ? `blocked-${row.id}` : undefined"
                @click="openDeactivate(row)"
              >Desactivar</UiButton>
              <span v-if="blocked(row)" :id="`blocked-${row.id}`" class="sr-only">{{ blocked(row) }}</span>
            </span>
          </LeoCan>
        </div>
      </template>
    </UiDataTable>

    <QueueCatalogFormModal
      v-if="formOpen"
      v-model:open="formOpen"
      :kind="kind"
      :item="editing"
      @saved="list.reload()"
    />

    <UiFormModal
      v-model:open="deactivateOpen"
      :title="`Desactivar ${info.noun}`"
      :description="deactivating ? `«${deactivating.name}» pasará a inactivo (no se elimina; se puede reactivar).` : undefined"
      size="sm"
      :submitting="deactivateForm.isSubmitting.value"
      :form-error="deactivateForm.formError.value"
      submit-label="Desactivar"
      @submit="onDeactivate"
    >
      <UiFormField name="reason" label="Motivo" required hint="Obligatorio. Queda en el historial.">
        <UiTextarea :rows="3" maxlength="255" />
      </UiFormField>
    </UiFormModal>

    <QueueSetDefaultModal
      v-if="defaulting"
      v-model:open="defaultOpen"
      :item="defaulting"
      :kind="kind"
      @saved="list.reload()"
    />

    <UiConfirmModal
      v-model:open="reactivation.open"
      :title="`Reactivar ${info.noun}`"
      :message="reactivation.target ? `«${reactivation.target.name}» volverá a estar activo.` : undefined"
      confirm-label="Reactivar"
      variant="primary"
      :loading="reactivation.loading"
      :error="reactivation.error"
      @confirm="reactivation.confirm()"
    />
  </div>
</template>

<script setup lang="ts">
import type { UiDataTableColumn } from '#andromeda/components/ui/UiDataTable.vue'
import type { QueueAdminItem, QueueAdminKind } from '../types'
import { canMakeDefault, deactivateBlockedReason, deactivateSchema, isPriorityKind, KIND_INFO, queueAdminErrorMessage } from '../utils/queueAdmin'
import { TAGS } from '../utils/tags'

const props = defineProps<{ kind: QueueAdminKind }>()

const info = KIND_INFO[props.kind]
const priority = isPriorityKind(props.kind)
const api = useQueueAdminApi(props.kind)
const list = useQueueAdminList(props.kind)
const toast = useToast()

const columns: UiDataTableColumn<QueueAdminItem>[] = [
  { key: 'name', label: 'Nombre' },
  { key: 'code', label: 'Código' },
  ...(priority ? [{ key: 'rank', label: 'Orden' } as UiDataTableColumn<QueueAdminItem>] : []),
  { key: 'is_active', label: 'Estado' },
  { key: 'updated_at', label: 'Actualizado' },
  { key: 'id', label: '', class: 'text-right' }
]

const blocked = (row: QueueAdminItem) => deactivateBlockedReason(props.kind, row)

// Crear / editar
const formOpen = ref(false)
const editing = ref<QueueAdminItem | null>(null)
function openCreate() {
  editing.value = null
  formOpen.value = true
}
function openEdit(row: QueueAdminItem) {
  editing.value = row
  formOpen.value = true
}

// Desactivar (motivo obligatorio)
const deactivateOpen = ref(false)
const deactivating = ref<QueueAdminItem | null>(null)
const deactivateForm = useZodForm(deactivateSchema, { initialValues: { reason: '' }, resetOn: deactivateOpen })
function openDeactivate(row: QueueAdminItem) {
  if (blocked(row)) return
  deactivating.value = row
  deactivateOpen.value = true
}
const onDeactivate = deactivateForm.submit(async ({ reason }) => {
  const row = deactivating.value
  if (!row) return
  try {
    await api.deactivate(row.id, reason)
  } catch (err) {
    // 409 (prioridad «media», última activa, ya inactiva): legible, dentro del modal.
    if ((err as { status?: number }).status === 409) {
      deactivateForm.formError.value = queueAdminErrorMessage(err, props.kind)
      return
    }
    throw err
  }
  toast.success(`«${row.name}» desactivado.`)
  deactivateOpen.value = false
  await list.reload()
})

// Hacer predeterminada (el modal es otro componente: dos formularios en uno comparten contexto)
const defaultOpen = ref(false)
const defaulting = ref<QueueAdminItem | null>(null)
function openSetDefault(row: QueueAdminItem) {
  if (!canMakeDefault(props.kind, row)) return
  defaulting.value = row
  defaultOpen.value = true
}

// Reactivar (confirmación)
const reactivation = useConfirmAction(
  async (row: QueueAdminItem) => {
    await api.activate(row.id)
    toast.success(`«${row.name}» reactivado.`)
    await list.reload()
  },
  { mapError: (err) => queueAdminErrorMessage(err, props.kind) }
)
</script>
