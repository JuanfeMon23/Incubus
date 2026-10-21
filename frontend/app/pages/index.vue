<template>
  <section v-if="!screens.length" class="mx-auto flex max-w-lg flex-col items-center gap-3 py-16 text-center">
    <h1 class="text-xl font-semibold">Tu usuario aún no tiene pantallas asignadas</h1>
    <p class="text-sm text-text-muted">
      Pide a un administrador que te asigne el rol de la etapa en la que trabajas
      (pre-recepción, recepción, etiquetas, toma de muestras, laboratorio o resultados).
    </p>
  </section>

  <section v-else class="mx-auto max-w-2xl space-y-4 py-8">
    <h1 class="text-xl font-semibold">¿A qué etapa vas a entrar?</h1>
    <p class="text-sm text-text-muted">Estas son las pantallas a las que tienes acceso.</p>
    <ul class="grid gap-3 sm:grid-cols-2">
      <li v-for="s in screens" :key="s.to">
        <NuxtLink
          :to="s.to"
          class="block rounded-xl border border-border bg-surface p-4 shadow-sm transition-colors hover:border-primary-400 hover:bg-primary-50"
        >
          <span class="block text-xs text-text-muted">{{ s.section }}</span>
          <span class="font-semibold">{{ s.label }}</span>
        </NuxtLink>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { firstVisibleRoute, visibleScreens } from '../utils/moduleAccess'

// Exige sesión (middleware global de leo-client), sin tag: cada usuario ve lo suyo.
definePageMeta({ leo: {} })

const { can } = useLeoSession()
const screens = visibleScreens(can)
// Con una sola etapa no hay nada que elegir: se entra directo.
if (screens.length === 1) await navigateTo(firstVisibleRoute(can), { replace: true })
</script>
