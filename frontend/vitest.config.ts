import { defineVitestConfig } from '@nuxt/test-utils/config'

export default defineVitestConfig({
  test: {
    // Vitest 5: la caché de módulos en disco rompe la segunda corrida ("Failed to resolve import ./composables/error.js").
    fsModuleCache: false,
    environment: 'nuxt',
    environmentOptions: {
      nuxt: {
        domEnvironment: 'happy-dom',
        overrides: { runtimeConfig: { public: { apiBase: 'http://api.test/api/v1' } } }
      }
    },
    include: ['app/components/**/*.test.ts']
  }
})
