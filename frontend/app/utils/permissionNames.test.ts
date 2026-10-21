import { describe, expect, it } from 'vitest'
import { forbiddenMessage, permissionName } from './permissionNames'
import { ALL_TAGS, TAGS } from './tags'

describe('catálogo de permisos', () => {
  it('son los 25 tags del backend, con formato incubus.<módulo>.<acción>', () => {
    expect(ALL_TAGS).toHaveLength(25)
    expect(new Set(ALL_TAGS).size).toBe(25)
    for (const tag of ALL_TAGS) expect(tag).toMatch(/^incubus\.[a-z-]+\.[a-z-]+$/)
  })

  it('cada tag tiene un nombre legible (no el tag técnico)', () => {
    for (const tag of ALL_TAGS) {
      const name = permissionName(tag)
      expect(name, tag).toBeTruthy()
      expect(name).not.toContain('incubus.')
      expect(name?.charAt(0)).toBe(name?.charAt(0).toUpperCase())
    }
  })

  it('el nombre de un tag desconocido o vacío es null', () => {
    expect(permissionName('incubus.otro.cosa')).toBeNull()
    expect(permissionName(undefined)).toBeNull()
  })
})

describe('forbiddenMessage', () => {
  it('nombra el permiso de details.action', () => {
    expect(forbiddenMessage({ action: TAGS.reception.callNext }, 'x')).toBe(
      'No tienes permiso para: Llamar al siguiente paciente'
    )
  })

  it('con any_of lista las alternativas sin repetir', () => {
    const msg = forbiddenMessage(
      { action: TAGS.reception.return, any_of: [TAGS.reception.return, TAGS.sampling.return] },
      'x'
    )
    expect(msg).toBe(
      'No tienes permiso para: Devolver pacientes a pre-recepción o Devolver pacientes a espera de toma'
    )
  })

  it('sin permiso conocido usa el mensaje de respaldo', () => {
    expect(forbiddenMessage({ action: 'incubus.x.y' }, 'No tienes permiso para realizar esta acción.')).toBe(
      'No tienes permiso para realizar esta acción.'
    )
    expect(forbiddenMessage(null, 'respaldo')).toBe('respaldo')
  })
})
