import type { ApiErrorBody } from '../types'

/** Mensaje legible de un error de la API (`{code, message}` o 422 de schema). */
export function apiErrorMessage(err: unknown): string {
  const data = (err as { data?: ApiErrorBody & { detail?: { msg: string }[] } })?.data
  if (data?.message) return data.message
  if (data?.detail?.length) return data.detail.map((d) => d.msg).join('; ')
  return (err as Error)?.message || 'Error inesperado.'
}

export function useApi() {
  const base = useRuntimeConfig().public.apiBase
  if (!base) throw new Error('Falta NUXT_PUBLIC_API_BASE (frontend/.env).')
  return <T>(path: string, opts: Parameters<typeof $fetch>[1] = {}) =>
    $fetch<T>(path, { baseURL: base, ...opts }) as Promise<T>
}
