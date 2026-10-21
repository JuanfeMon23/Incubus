import type { LeoRequestOptions } from '#leo-client/lib/transport'
import type { ForbiddenDetails } from '../utils/permissionNames'

/**
 * Mensaje legible para el usuario (regla de todas las apps: nunca el texto
 * crudo de fetch ni de la API). Delegado a `leoErrorMessage` de leo-client
 * (que usa `toUserMessage` de Andromeda para red/5xx/desconocidos).
 */
export function apiErrorMessage(err: unknown): string {
  return leoErrorMessage(err)
}

/** Opciones de una llamada (mismas que `LeoRequestOptions`; `params` no existe, usa `query`). */
export type ApiOptions = Pick<LeoRequestOptions, 'method' | 'body' | 'query' | 'signal' | 'responseType'>

/** Un 403 `forbidden` nombra el permiso que falta ("No tienes permiso para: …"). */
function withPermissionName(err: unknown): unknown {
  if (err instanceof LeoApiError && err.status === 403 && err.code === 'forbidden') {
    const message = forbiddenMessage(err.details as ForbiddenDetails | null, err.message)
    return new LeoApiError(err.status, err.code, message, err.details, err.retryAfterSeconds)
  }
  return err
}

/**
 * Cliente HTTP de Incubus: toda llamada a la API pasa por el solicitante
 * firmado de leo-client (`useLeoApi`: cookie + DPoP) contra UNA sola URL de
 * backend. Un 401 de sesión lleva al login (lo hace leo-client). Los errores
 * son `LeoApiError`; para mostrarlos usa `apiErrorMessage`.
 *
 * `api<T>('/queue', { method: 'POST', body })`; `responseType: 'blob'` para archivos.
 */
export function useApi() {
  const { apiBase, leo } = useRuntimeConfig().public
  if (!apiBase) throw new Error('Falta NUXT_PUBLIC_API_BASE (frontend/.env).')
  const leoApi = useLeoApi()
  return async <T>(path: string, options: ApiOptions = {}): Promise<T> => {
    try {
      return await leoApi<T>(toLeoPath(apiBase, leo.apiBase, path), options)
    } catch (err) {
      throw withPermissionName(err)
    }
  }
}
