import { describe, expect, it } from 'vitest'
import { ageFrom, formatDuration, fullName, waitingLabel, originFromApiBase } from './format'

describe('format', () => {
  it('formatDuration', () => {
    expect(formatDuration(12, 'horas')).toBe('12 h')
    expect(formatDuration(1.5, 'dias')).toBe('1.5 d')
    expect(formatDuration(null, null)).toBe('')
  })

  it('fullName omite vacíos', () => {
    expect(
      fullName({ first_name: 'JUAN', second_name: null, first_last_name: 'GOMEZ', second_last_name: 'RUIZ' })
    ).toBe('JUAN GOMEZ RUIZ')
  })

  it('ageFrom respeta el cumpleaños', () => {
    const today = new Date('2026-10-13T12:00:00')
    expect(ageFrom('1985-10-14', today)).toBe(40)
    expect(ageFrom('1985-10-13', today)).toBe(41)
    expect(ageFrom(null, today)).toBeNull()
  })

  it('originFromApiBase', () => {
    expect(originFromApiBase('http://localhost:8001/api/v1')).toBe('http://localhost:8001')
    expect(originFromApiBase('https://api.lab.co/api/v1')).toBe('https://api.lab.co')
  })

  it('waitingLabel', () => {
    const now = new Date('2026-10-13T10:00:00Z').getTime()
    expect(waitingLabel('2026-10-13T09:45:00Z', now)).toBe('15 min')
    expect(waitingLabel('2026-10-13T08:30:00Z', now)).toBe('1 h 30 min')
  })
})
