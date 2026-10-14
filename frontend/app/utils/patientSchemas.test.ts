import { describe, expect, it } from 'vitest'
import { intakePatientSchema, receptionPatientSchema } from './patientSchemas'

const valid = {
  first_name: 'Juan',
  second_name: '',
  first_last_name: 'Gómez',
  second_last_name: '',
  birth_date: '1985-03-12',
  birth_place: 'Bogotá',
  sex: 'M',
  blood_type: 'O+',
  email: 'juan@correo.co',
  phone: '300 111 2233',
  insurer: 'EPS Salud',
  address: 'Calle 1 # 2-3'
}

function errorsOf(input: Record<string, unknown>) {
  const result = receptionPatientSchema.safeParse(input)
  if (result.success) return {}
  return Object.fromEntries(result.error.issues.map((i) => [String(i.path[0]), i.message]))
}

describe('receptionPatientSchema', () => {
  it('acepta un paciente completo (segundos nombre/apellido opcionales)', () => {
    const out = receptionPatientSchema.parse(valid)
    expect(out.second_name).toBeNull()
    expect(out.first_name).toBe('Juan')
  })

  it('cada campo obligatorio vacío da su mensaje', () => {
    const required = [
      'first_name', 'first_last_name', 'birth_date', 'birth_place',
      'sex', 'blood_type', 'email', 'phone', 'insurer', 'address'
    ]
    for (const key of required) {
      const errors = errorsOf({ ...valid, [key]: '' })
      expect(errors[key], key).toMatch(/obligatori/)
    }
  })

  it('valida formato de correo, teléfono y fecha futura', () => {
    expect(errorsOf({ ...valid, email: 'no-es-correo' }).email).toMatch(/correo/)
    expect(errorsOf({ ...valid, phone: 'abc' }).phone).toMatch(/teléfono/)
    expect(errorsOf({ ...valid, birth_date: '2999-01-01' }).birth_date).toMatch(/futura/)
  })

  it('el sexo solo admite M o F', () => {
    expect(errorsOf({ ...valid, sex: 'X' }).sex).toBeTruthy()
  })
})

describe('intakePatientSchema', () => {
  const base = {
    document_number: '1020304050',
    first_name: 'JUAN',
    second_name: '',
    first_last_name: 'GOMEZ',
    second_last_name: '',
    sex: '',
    birth_date: '',
    blood_type: '',
    priority_id: 'abc'
  }

  it('exige documento, nombre, apellido y prioridad', () => {
    expect(intakePatientSchema.safeParse(base).success).toBe(true)
    for (const key of ['document_number', 'first_name', 'first_last_name', 'priority_id']) {
      expect(intakePatientSchema.safeParse({ ...base, [key]: '' }).success, key).toBe(false)
    }
  })

  it('normaliza vacíos a null', () => {
    const out = intakePatientSchema.parse(base)
    expect(out.sex).toBeNull()
    expect(out.birth_date).toBeNull()
    expect(out.blood_type).toBeNull()
  })
})
