export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  // Sistema de diseño compartido (Andromeda) + sesión SSO y permisos del
  // ecosistema (leo-client, dependencia git fijada a una etiqueta del repo de
  // Leo). Andromeda va primero: los componentes de leo-client usan sus Ui* y tokens.
  // leo-client fuerza SPA (`ssr: false`): Incubus no usa SSR.
  extends: ['andromeda', 'leo-client'],
  typescript: {
    // La config de la capa leo-client (dependencia) no se chequea desde aquí.
    tsConfig: { exclude: ['../node_modules/leo-client/**', '../node_modules/.pnpm/leo-client*/**'] }
  },
  runtimeConfig: {
    public: {
      // Se llena desde NUXT_PUBLIC_API_BASE (frontend/.env). Ej.: http://localhost:8001/api/v1
      // Debe colgar de NUXT_PUBLIC_LEO_API_BASE (una sola URL de backend).
      apiBase: '',
      // Claves definidas por leo-client; aquí los valores fijos de Incubus (transporte `bff`).
      // `apiBase` y `publicUrl` vienen del .env (NUXT_PUBLIC_LEO_API_BASE / _PUBLIC_URL).
      leo: {
        transport: 'bff',
        authPath: '/auth',
        // Debe coincidir con la redirect_uri registrada en Leo: http://localhost:3200/leo/callback
        callbackPath: '/leo/callback',
        appSlug: 'incubus',
        appName: 'Incubus'
      }
    }
  }
})
