<template>
  <div class="min-h-screen bg-zinc-50 text-zinc-900">
    <header class="border-b border-zinc-200 bg-white">
      <nav class="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <span class="text-lg font-semibold tracking-tight">Incubus</span>
        <NuxtLink to="/pre-recepcion" class="nav-link" active-class="nav-active">Pre-recepción</NuxtLink>
        <NuxtLink to="/recepcion" class="nav-link" active-class="nav-active">Recepción</NuxtLink>
        <span class="ml-auto text-xs" :class="live ? 'text-emerald-600' : 'text-amber-600'">
          {{ live ? '● en vivo' : '● reconectando…' }}
        </span>
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

<style>
.nav-link { color: #52525b; font-size: 0.875rem; }
.nav-active { color: #18181b; font-weight: 600; }
</style>
