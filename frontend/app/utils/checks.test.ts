import { describe, expect, it } from 'vitest'
import { checksComplete, emptyChecks, missingNoteKeys, toCheckPayload, unansweredKeys } from './checks'

describe('checks', () => {
  it('emptyChecks deja todo sin responder', () => {
    const c = emptyChecks(['a', 'b'])
    expect(unansweredKeys(['a', 'b'], c)).toEqual(['a', 'b'])
    expect(checksComplete(['a', 'b'], c)).toBe(false)
  })

  it('"no cumple" exige nota', () => {
    const c = { a: { met: false, note: '  ' }, b: { met: true, note: '' } }
    expect(missingNoteKeys(['a', 'b'], c)).toEqual(['a'])
    expect(checksComplete(['a', 'b'], c)).toBe(false)
    c.a.note = 'comió'
    expect(checksComplete(['a', 'b'], c)).toBe(true)
  })

  it('sin precondiciones no hay nada pendiente', () => {
    expect(checksComplete([], {})).toBe(true)
  })

  it('toCheckPayload normaliza notas vacías a null', () => {
    const payload = toCheckPayload(['a', 'b'], {
      a: { met: true, note: ' ' },
      b: { met: false, note: ' nota ' }
    })
    expect(payload).toEqual([
      { key: 'a', met: true, note: null },
      { key: 'b', met: false, note: 'nota' }
    ])
  })
})
