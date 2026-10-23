<template>
  <UiSettingsPanel :admin="admin" />
</template>

<script setup lang="ts">
import { TAGS } from '../utils/tags'

// Pantalla: settings.view. Editar se condiciona por permiso (edit / edit-security) dentro del panel.
definePageMeta({ leo: { tag: TAGS.settings.view } })

const admin = useSettingsScreen()
</script>
