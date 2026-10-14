import { defineVitestConfig } from '@nuxt/test-utils/config'

export default defineVitestConfig({
  test: {
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
