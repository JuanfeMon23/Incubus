import { defineVitestConfig } from '@nuxt/test-utils/config'

export default defineVitestConfig({
  test: {
    // Vitest 5: la caché de módulos en disco rompe la segunda corrida ("Failed to resolve import ./composables/error.js").
    fsModuleCache: false,
    environment: 'nuxt',
    environmentOptions: {
      nuxt: {
        domEnvironment: 'happy-dom',
        // Valores falsos propios de los tests: no dependen de `frontend/.env`.
        overrides: {
          runtimeConfig: {
            public: {
              apiBase: 'http://api.test/api/v1',
              // leo-client en `bff` contra una API falsa (apiBase cuelga de leo.apiBase).
              leo: { transport: 'bff', apiBase: 'http://api.test', publicUrl: 'http://api.test', appSlug: 'incubus', appName: 'Incubus' }
            }
          }
        }
      }
    },
    // Lo puro de app/utils corre en el config unitario (node), salvo lo que necesita Nuxt.
    include: [
      'app/components/**/*.test.ts',
      'app/pages/**/*.test.ts',
      'app/layouts/**/*.test.ts',
      'app/composables/**/*.test.ts',
      'app/utils/leoConfig.test.ts'
    ]
  }
})
