<template>
  <div class="min-h-screen bg-background text-text">
    <header class="border-b border-border bg-surface">
      <nav class="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3">
        <span class="mr-4 text-lg font-semibold tracking-tight">Incubus</span>
        <UiButton to="/pre-recepcion" variant="ghost" size="sm">Pre-recepción</UiButton>
        <UiButton to="/recepcion" variant="ghost" size="sm">Recepción</UiButton>
        <UiButton to="/toma-muestras" variant="ghost" size="sm">Toma de muestras</UiButton>
        <UiStatusBadge
          class="ml-auto"
          dot
          :variant="live ? 'success' : 'warning'"
          :label="live ? 'En vivo' : 'Reconectando…'"
        />
      </nav>
    </header>
    <main class="mx-auto max-w-6xl px-4 py-6">
      <NuxtPage />
    </main>
  </div>
</template>

<script setup lang="ts">
const { live } = useQueueSocket()
</script>
