export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  // Sistema de diseño compartido (Andromeda): componentes Ui*, tokens y estilos.
  extends: ['../../andromeda'],
  runtimeConfig: {
    public: {
      // Se llena desde NUXT_PUBLIC_API_BASE (frontend/.env). Ej.: http://localhost:8001/api/v1
      apiBase: ''
    }
  }
})
