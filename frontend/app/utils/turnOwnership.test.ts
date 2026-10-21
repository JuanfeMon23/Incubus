import { describe, expect, it } from 'vitest'
import { canActOnTurn, isNotTurnOwnerError, turnOwnerHint } from './turnOwnership'

const turn = (owner: string | null, id: string | null) => ({ claimed_by: owner, claimed_by_user_id: id })

describe('canActOnTurn', () => {
  it('el dueño del turno puede actuar', () => {
    expect(canActOnTurn(turn('Ana', 'u1'), { id: 'u1' }, false)).toBe(true)
  })
  it('otra persona no puede actuar', () => {
    expect(canActOnTurn(turn('Ana', 'u1'), { id: 'u2' }, false)).toBe(false)
  })
  it('un supervisor puede actuar en turnos ajenos', () => {
    expect(canActOnTurn(turn('Ana', 'u1'), { id: 'u2' }, true)).toBe(true)
  })
  it('turno legado (dueño desconocido) no restringe más que el permiso normal', () => {
    expect(canActOnTurn(turn('Ana', null), { id: 'u2' }, false)).toBe(true)
    expect(canActOnTurn({ claimed_by: 'Ana' }, { id: 'u2' }, false)).toBe(true)
  })
  it('sin sesión no puede actuar en un turno con dueño, pero sí en uno legado', () => {
    expect(canActOnTurn(turn('Ana', 'u1'), null, false)).toBe(false)
    expect(canActOnTurn(turn('Ana', null), null, false)).toBe(true)
  })
})

describe('turnOwnerHint', () => {
  it('nombra al dueño', () => {
    expect(turnOwnerHint({ claimed_by: 'Ana Pérez' }, 'devolverlo')).toBe(
      'Este turno lo tomó Ana Pérez. Solo esa persona (o un supervisor) puede devolverlo.'
    )
  })
  it('sin nombre dice "otra persona"', () => {
    expect(turnOwnerHint({ claimed_by: null }, 'finalizarlo')).toContain('otra persona')
  })
})

describe('isNotTurnOwnerError', () => {
  it('reconoce el 403 not_turn_owner', () => {
    expect(isNotTurnOwnerError({ status: 403, code: 'not_turn_owner' })).toBe(true)
  })
  it('ignora otros errores', () => {
    expect(isNotTurnOwnerError({ status: 403, code: 'forbidden' })).toBe(false)
    expect(isNotTurnOwnerError(new Error('x'))).toBe(false)
    expect(isNotTurnOwnerError(null)).toBe(false)
  })
})
