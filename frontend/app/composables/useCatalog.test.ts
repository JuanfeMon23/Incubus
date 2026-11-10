import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const fake = await vi.hoisted(async () => (await import('~/testing/fakeApi')).createFakeApi())
mockNuxtImport('useLeoAppApi', () => () => fake.client)

beforeEach(() => fake.reset())

describe('useCatalog', () => {
  it('pide /catalogs/{slug} con caché y expone opciones y nombres', async () => {
    fake.routes['GET /catalogs/sexes'] = [
      { code: 'male', name: 'Hombre', sort_order: 1, is_active: true },
      { code: 'female', name: 'Mujer', sort_order: 2, is_active: true }
    ]
    const sexes = useCatalog('sexes')
    await sexes.ready
    expect(fake.requests).toHaveBeenCalledWith('GET', '/catalogs/sexes', expect.objectContaining({ cacheTtl: expect.any(Number) }))
    expect(sexes.options.value).toEqual([{ value: 'male', label: 'Hombre' }, { value: 'female', label: 'Mujer' }])
    expect(sexes.nameOf('female')).toBe('Mujer')
    expect(sexes.nameOf('M', '—')).toBe('—')
  })

  it('includeInactive pide todos los registros', async () => {
    const statuses = useCatalog('queue-statuses', { includeInactive: true })
    await statuses.ready
    expect(fake.requests).toHaveBeenCalledWith('GET', '/catalogs/queue-statuses', expect.objectContaining({ query: { include_inactive: true } }))
  })

  it('un fallo deja el catálogo vacío y un mensaje legible', async () => {
    fake.routes['GET /catalogs/blood-types'] = () => Promise.reject(new TypeError('Failed to fetch'))
    const bloodTypes = useCatalog('blood-types')
    await bloodTypes.ready
    expect(bloodTypes.items.value).toEqual([])
    expect(bloodTypes.error.value).not.toMatch(/fetch/i)
  })
})
