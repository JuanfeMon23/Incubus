<template>
  <!-- Sin redirección posible: el layout (menú y barra superior con cerrar sesión) sigue visible. -->
  <section v-if="!target" class="mx-auto flex max-w-lg flex-col items-center gap-3 py-16 text-center">
    <h1 class="text-xl font-semibold">Sin acceso</h1>
    <p class="text-sm text-text-muted">
      Tu usuario no tiene acceso a ninguna pantalla de Incubus. Pide a un administrador de Leo que te asigne un rol.
    </p>
  </section>
</template>

<script setup lang="ts">
import { firstVisibleRoute } from '../utils/moduleAccess'

// Exige sesión (middleware global de leo-client, que la resuelve antes de renderizar), sin tag.
definePageMeta({ leo: {} })

// Entra directo al primer módulo del menú al que tenga acceso; `replace` evita que "atrás" rebote a `/`.
const { can } = useLeoSession()
const target = firstVisibleRoute(can)
if (target) await navigateTo(target, { replace: true })
</script>
