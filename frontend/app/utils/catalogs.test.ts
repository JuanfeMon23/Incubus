import { describe, expect, it } from 'vitest'
import { catalogNameOf, catalogOptions, flagPresentation, namesByCode } from './catalogs'

const SEXES = [
  { code: 'male', name: 'Hombre', sort_order: 1, is_active: true },
  { code: 'female', name: 'Mujer', sort_order: 2, is_active: true }
]

describe('catalogs', () => {
  it('arma opciones con el nombre, o con «code · nombre»', () => {
    expect(catalogOptions(SEXES)).toEqual([{ value: 'male', label: 'Hombre' }, { value: 'female', label: 'Mujer' }])
    expect(catalogOptions(SEXES, { withCode: true })[0]).toEqual({ value: 'male', label: 'male · Hombre' })
  })
  it('mapea code a nombre y usa el fallback si no existe', () => {
    expect(namesByCode(SEXES)).toEqual({ male: 'Hombre', female: 'Mujer' })
    expect(catalogNameOf(SEXES, 'female')).toBe('Mujer')
    expect(catalogNameOf(SEXES, 'x', '—')).toBe('—')
    expect(catalogNameOf(SEXES, null, '—')).toBe('—')
  })
  it('la bandera sale del catálogo result-flags', () => {
    const flags = [{ code: 'critical_high', name: 'Crítico alto', sort_order: 1, is_active: true, variant: 'danger' as const, show_in_report: true }]
    expect(flagPresentation(flags, 'critical_high')).toEqual({ variant: 'danger', label: 'Crítico alto' })
    expect(flagPresentation(flags, 'otra')).toBeNull()
    expect(flagPresentation(flags, null)).toBeNull()
  })
})
