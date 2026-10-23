import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

// Lógica pura (utilidades, schemas): sin Nuxt, rápida y estable.
export default defineConfig({
  resolve: {
    alias: {
      '#andromeda': fileURLToPath(new URL('./node_modules/andromeda/app', import.meta.url)),
      '#leo-client': fileURLToPath(new URL('./node_modules/leo-client/app', import.meta.url))
    }
  },
  test: {
    environment: 'node',
    include: ['app/utils/**/*.test.ts'],
    // Necesita el entorno Nuxt (runtimeConfig/router): corre con `vitest run`.
    exclude: ['app/utils/leoConfig.test.ts']
  }
})
