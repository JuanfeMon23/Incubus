/**
 * Mensaje legible para el usuario (regla de todas las apps: nunca el texto
 * crudo de fetch ni de la API). Delegado a `toUserMessage` de Andromeda.
 */
export function apiErrorMessage(err: unknown): string {
  return toUserMessage(err)
}

export function useApi() {
  const base = useRuntimeConfig().public.apiBase
  if (!base) throw new Error('Falta NUXT_PUBLIC_API_BASE (frontend/.env).')
  return <T>(path: string, opts: Parameters<typeof $fetch>[1] = {}) =>
    $fetch<T>(path, { baseURL: base, ...opts }) as Promise<T>
}
