import { describe, expect, it } from 'vitest'
import { enteredByLabel, validationLabels } from './resultAuthorship'

describe('enteredByLabel', () => {
  it('"Tú" si el usuario actual capturó el valor', () => {
    expect(enteredByLabel({ entered_by: 'Ana Pérez', entered_by_user_id: 'u1' }, 'u1')).toBe('Capturado por Tú')
  })
  it('nombre de quien capturó si es otra persona', () => {
    expect(enteredByLabel({ entered_by: 'Luis Gómez', entered_by_user_id: 'u2' }, 'u1')).toBe('Capturado por Luis Gómez')
  })
  it('sin id usa el nombre; sin nada, no muestra nada (ni ids)', () => {
    expect(enteredByLabel({ entered_by: 'Luis Gómez' }, 'u1')).toBe('Capturado por Luis Gómez')
    expect(enteredByLabel({ entered_by: null, entered_by_user_id: 'u2' }, 'u1')).toBeNull()
    expect(enteredByLabel({}, 'u1')).toBeNull()
  })
})

describe('validationLabels', () => {
  it('profesional que firma y usuario que ejecutó, por separado', () => {
    expect(validationLabels({ validated_by: 'Dra. Mora', validated_by_user: 'Luis Gómez', validated_by_user_id: 'u2' }, 'u1')).toEqual({
      professional: 'Validado por Dra. Mora (profesional)',
      executor: 'Validación ejecutada por Luis Gómez'
    })
  })
  it('"Tú" si el usuario actual ejecutó la validación, aunque solo venga el id', () => {
    expect(validationLabels({ validated_by: 'Dra. Mora', validated_by_user_id: 'u1' }, 'u1').executor).toBe('Validación ejecutada por Tú')
  })
  it('solo id de otro usuario y sin nombre: se omite, nunca se muestra el id', () => {
    const l = validationLabels({ validated_by: 'Dra. Mora', validated_by_user_id: 'u-xyz' }, 'u1')
    expect(l.executor).toBeNull()
    expect(JSON.stringify(l)).not.toContain('u-xyz')
  })
  it('sin profesional no hay línea de profesional', () => {
    expect(validationLabels({ validated_by: null }, 'u1').professional).toBeNull()
  })
})
