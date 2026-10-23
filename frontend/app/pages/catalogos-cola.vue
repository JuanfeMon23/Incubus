<template>
  <div class="space-y-6">
    <UiPageHeader
      title="Catálogos de la cola"
      description="Prioridades y motivos de retiro y devolución que usan recepción y pre-recepción. Nada se elimina: se desactiva."
    />
    <UiTabs v-model="activeTab" :tabs="tabs" aria-label="Catálogos de la cola">
      <template v-for="kind in QUEUE_ADMIN_KINDS" :key="kind" #[kind]>
        <QueueCatalogPanel :kind="kind" />
      </template>
    </UiTabs>
  </div>
</template>

<script setup lang="ts">
import { KIND_INFO, QUEUE_ADMIN_KINDS } from '../utils/queueAdmin'
import { TAGS } from '../utils/tags'

// Pantalla: queue-admin.view. Crear/editar/activar se condicionan por botón (create/update/toggle).
definePageMeta({ leo: { tag: TAGS.queueAdmin.view } })

const tabs = QUEUE_ADMIN_KINDS.map((kind) => ({ key: kind, label: KIND_INFO[kind].tab }))
const activeTab = ref<string>(QUEUE_ADMIN_KINDS[0]!)
</script>
