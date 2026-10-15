<template>
  <div class="min-h-screen bg-background text-text">
    <UiSidebar
      v-model:collapsed="collapsedPad"
      :items="menu"
      brand="Incubus"
      storage-key="incubus.sidebar.collapsed"
    >
      <template #footer="{ collapsed }">
        <UiStatusBadge
          v-if="!collapsed"
          dot
          :variant="live ? 'success' : 'warning'"
          :label="live ? 'En vivo' : 'Reconectando…'"
        />
        <span
          v-else
          class="h-3 w-3 rounded-full"
          :class="live ? 'bg-success-500' : 'bg-warning-500'"
          :title="live ? 'En vivo' : 'Reconectando…'"
        />
      </template>
    </UiSidebar>

    <!-- El contenido deja el espacio de la barra lateral en pantallas grandes -->
    <div class="transition-all duration-200 lg:pl-64" :class="{ 'lg:!pl-[4.5rem]': collapsedPad }">
      <main class="mx-auto max-w-6xl px-4 py-6">
        <NuxtPage />
      </main>
    </div>
    <UiToaster />
  </div>
</template>

<script setup lang="ts">
import type { UiSidebarItem } from '#andromeda/components/ui/UiSidebar.vue'

const { live } = useQueueSocket()

// Iconos de trazo 24×24 (atributo `d` del path).
const ICONS = {
  intake: 'M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.5 20.118a7.5 7.5 0 0 1 15 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.5-1.632Z',
  reception: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2ZM9 12h6M9 16h4',
  printer: 'M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v7H6v-7Z',
  sample: 'M12 2.5s6 6.2 6 10.5a6 6 0 0 1-12 0C6 8.7 12 2.5 12 2.5Z',
  inbox: 'M4 13h4l1 3h6l1-3h4M4 13V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7M4 13v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5',
  results: 'M9 3h6M10 3v6l-5.5 9.5A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-2.5L14 9V3'
}

const menu: UiSidebarItem[] = [
  { section: 'Atención', label: 'Pre-recepción', to: '/pre-recepcion', icon: ICONS.intake },
  { section: 'Atención', label: 'Recepción', to: '/recepcion', icon: ICONS.reception },
  { section: 'Toma de muestras', label: 'Impresión de etiquetas', to: '/impresion-etiquetas', icon: ICONS.printer },
  { section: 'Toma de muestras', label: 'Toma de muestras', to: '/toma-muestras', icon: ICONS.sample },
  { section: 'Laboratorio', label: 'Recepción laboratorio', to: '/recepcion-laboratorio', icon: ICONS.inbox },
  { section: 'Laboratorio', label: 'Resultados', to: '/resultados', icon: ICONS.results }
]

// La barra avisa si está contraída para ajustar el margen del contenido.
const collapsedPad = ref(false)
</script>
