import { describe, expect, it } from 'vitest'
import { PERMISSION_NAMES } from './permissionNames'
import { ALL_TAGS } from './tags'

describe('catálogo de permisos', () => {
  it('los tags asignables tienen formato incubus.<módulo>.<acción> y no se repiten', () => {
    expect(ALL_TAGS.length).toBeGreaterThan(0)
    expect(new Set(ALL_TAGS).size).toBe(ALL_TAGS.length)
    for (const tag of ALL_TAGS) expect(tag).toMatch(/^incubus\.[a-z-]+\.[a-z-]+$/)
  })

  it('cada tag tiene un nombre legible (no el tag técnico)', () => {
    for (const tag of ALL_TAGS) {
      const name = PERMISSION_NAMES[tag]
      expect(name, tag).toBeTruthy()
      expect(name).not.toContain('incubus.')
      expect(name?.charAt(0)).toBe(name?.charAt(0).toUpperCase())
    }
  })

  it('un tag desconocido no tiene nombre', () => {
    expect(PERMISSION_NAMES['incubus.otro.cosa']).toBeUndefined()
  })
})
