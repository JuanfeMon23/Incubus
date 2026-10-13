import tailwindcss from '@tailwindcss/vite'

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  vite: { plugins: [tailwindcss()] },
  runtimeConfig: {
    public: {
      // Se llena desde NUXT_PUBLIC_API_BASE (frontend/.env). Ej.: http://localhost:8001/api/v1
      apiBase: ''
    }
  }
})
