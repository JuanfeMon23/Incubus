import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'

// Vitest 5 da como error del test la promesa rechazada que devuelve un mock aunque el código la capture:
// el rechazo se arma en una función simple (`state.next`), fuera de `vi.fn`.
const leoApi = vi.hoisted(() => vi.fn())
const state = vi.hoisted(() => ({ next: (): Promise<unknown> => Promise.resolve(undefined) }))
mockNuxtImport('useLeoApi', () => () => (path: string, options?: unknown) => {
  leoApi(path, options)
  return state.next()
})
const resolveWith = (value: unknown) => { state.next = () => Promise.resolve(value) }
const rejectWith = (...errors: unknown[]) => {
  const queue = [...errors]
  state.next = () => Promise.reject(queue.length > 1 ? queue.shift() : queue[0])
}

beforeEach(() => leoApi.mockReset())

describe('useApi', () => {
  it('pasa por el solicitante firmado de leo-client con la ruta bajo /api/v1 de la misma URL de backend', async () => {
    resolveWith([{ id: 1 }])
    const result = await useApi()('/queue', { query: { status: ['a', 'b'] } })
    expect(result).toEqual([{ id: 1 }])
    expect(leoApi).toHaveBeenCalledWith('/api/v1/queue', { query: { status: ['a', 'b'] } })
  })

  it('pide archivos como blob (etiquetas) por el mismo camino firmado', async () => {
    resolveWith(new Blob(['x']))
    await useApi()('/orders/by-entry/e1/labels.pdf', { responseType: 'blob' })
    expect(leoApi).toHaveBeenCalledWith('/api/v1/orders/by-entry/e1/labels.pdf', { responseType: 'blob' })
  })

  it('un 403 forbidden nombra el permiso que falta', async () => {
    rejectWith(
      new LeoApiError(403, 'forbidden', 'No tienes permiso para realizar esta acción.', {
        action: 'incubus.reception.call-next'
      })
    )
    const err = await useApi()('/queue/call-next', { method: 'POST' }).catch((e) => e)
    expect(err).toBeInstanceOf(LeoApiError)
    expect(apiErrorMessage(err)).toBe('No tienes permiso para: Llamar al siguiente paciente')
  })

  it('un 403 con any_of lista las alternativas; sin permiso conocido deja el mensaje del servidor', async () => {
    rejectWith(
      new LeoApiError(403, 'forbidden', 'x', {
        action: 'incubus.reception.return',
        any_of: ['incubus.reception.return', 'incubus.sampling.return']
      })
    )
    expect(apiErrorMessage(await useApi()('/queue/1/return').catch((e) => e))).toBe(
      'No tienes permiso para: Devolver pacientes a pre-recepción o Devolver pacientes a espera de toma'
    )
    rejectWith(new LeoApiError(403, 'forbidden', 'No tienes permiso para realizar esta acción.', {}))
    expect(apiErrorMessage(await useApi()('/x').catch((e) => e))).toBe('No tienes permiso para realizar esta acción.')
  })

  it('otros errores conservan su mensaje legible (y los de red no muestran texto crudo)', async () => {
    rejectWith(new LeoApiError(409, 'conflict', 'El paciente ya fue tomado.', null))
    expect(apiErrorMessage(await useApi()('/x').catch((e) => e))).toBe('El paciente ya fue tomado.')
    rejectWith(new TypeError('Failed to fetch'))
    expect(apiErrorMessage(await useApi()('/x').catch((e) => e))).not.toContain('Failed to fetch')
  })
})
