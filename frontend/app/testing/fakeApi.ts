import { vi } from 'vitest'

/**
 * `useLeoAppApi` falso para tests de páginas/composables (solo tests; Nuxt no
 * auto-importa `app/testing/`). `useLeoAppApi()` devuelve los verbos
 * `get/post/patch/put/delete` (`client`); `api` es la función común por debajo.
 *
 * - `routes['GET /ruta']`: respuesta (valor o función del body/opciones). Una
 *   ruta sin simular responde `[]` si es GET (listas vacías) y el body si no.
 * - `requests`: spy de cada llamada `(método, ruta, opciones)`.
 * - `bodies(método, ruta)`: los bodies enviados, en orden.
 *
 * Uso (el factory de `mockNuxtImport` se iza: el fake se crea con `vi.hoisted`):
 * ```ts
 * const fake = await vi.hoisted(async () => (await import('~/testing/fakeApi')).createFakeApi())
 * mockNuxtImport('useLeoAppApi', () => () => fake.client)
 * beforeEach(() => fake.reset())
 * ```
 */
export type FakeApiHandler = unknown | ((input: unknown) => unknown)
interface FakeOptions { method?: string, body?: unknown, query?: unknown }

export function createFakeApi() {
  const routes: Record<string, FakeApiHandler> = {}
  const requests = vi.fn<(method: string, path: string, options?: FakeOptions) => void>()

  const api = (path: string, options: FakeOptions = {}): Promise<unknown> => {
    const method = options.method ?? 'GET'
    const key = `${method} ${path.split('?')[0]}`
    requests(method, path, options)
    if (!(key in routes)) return Promise.resolve(method === 'GET' ? [] : options.body)
    const handler = routes[key]
    return Promise.resolve(typeof handler === 'function' ? (handler as (input: unknown) => unknown)(options) : handler)
  }

  const verb = (method: string) => <T>(path: string, ...rest: unknown[]): Promise<T> => {
    const hasBody = method !== 'GET' && method !== 'DELETE'
    const options = ((hasBody ? rest[1] : rest[0]) ?? {}) as Omit<FakeOptions, 'method' | 'body'>
    return api(path, { ...options, ...(method !== 'GET' ? { method } : {}), ...(hasBody && rest[0] !== undefined ? { body: rest[0] } : {}) }) as Promise<T>
  }
  /** Verbos de `useLeoAppApi()`. */
  const client = {
    get: verb('GET'),
    post: verb('POST'),
    patch: verb('PATCH'),
    put: verb('PUT'),
    delete: verb('DELETE')
  }

  /** Bodies enviados con ese método a esa ruta, en orden. */
  function bodies(method: string, path: string) {
    return requests.mock.calls.filter(([m, p]) => m === method && p === path).map(([, , o]) => o?.body)
  }

  function reset() {
    for (const key of Object.keys(routes)) delete routes[key]
    requests.mockReset()
  }

  return { api, client, routes, requests, bodies, reset }
}
