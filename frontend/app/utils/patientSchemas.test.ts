import { describe, expect, it } from 'vitest'
import {
  BLOOD_TYPES,
  digitsOnly,
  intakePatientSchema,
  receptionPatientSchema,
  todayISO
} from './patientSchemas'

const valid = {
  document_type: 'CC',
  document_number: '1020304050',
  first_name: 'Juan',
  second_name: '',
  first_last_name: 'Gómez',
  second_last_name: '',
  birth_date: '1985-03-12',
  birth_place: 'Bogotá',
  sex: 'M',
  blood_type: 'O+',
  email: 'juan@correo.co',
  phone: '3001112233',
  insurer: '',
  address: 'Calle 1 # 2-3'
}

function errorsOf(input: Record<string, unknown>) {
  const result = receptionPatientSchema.safeParse(input)
  if (result.success) return {}
  return Object.fromEntries(result.error.issues.map((i) => [String(i.path[0]), i.message]))
}

describe('receptionPatientSchema', () => {
  it('acepta un paciente completo; segundos nombre/apellido y aseguradora opcionales', () => {
    const out = receptionPatientSchema.parse(valid)
    expect(out.second_name).toBeNull()
    expect(out.insurer).toBeNull()
  })

  it('cada campo obligatorio vacío da su mensaje', () => {
    const required = [
      'document_type', 'document_number', 'first_name', 'first_last_name', 'birth_date',
      'birth_place', 'sex', 'blood_type', 'email', 'phone', 'address'
    ]
    for (const key of required) {
      expect(errorsOf({ ...valid, [key]: '' })[key], key).toMatch(/obligatori/)
    }
  })

  it('la aseguradora no es obligatoria', () => {
    expect(errorsOf({ ...valid, insurer: '' }).insurer).toBeUndefined()
  })

  it('la fecha de nacimiento no puede ser posterior a hoy', () => {
    expect(errorsOf({ ...valid, birth_date: '2999-01-01' }).birth_date).toMatch(/posterior a hoy/)
    expect(errorsOf({ ...valid, birth_date: todayISO() }).birth_date).toBeUndefined()
  })

  it('el RH solo admite los 8 valores válidos', () => {
    for (const rh of BLOOD_TYPES) expect(errorsOf({ ...valid, blood_type: rh }).blood_type).toBeUndefined()
    expect(errorsOf({ ...valid, blood_type: 'Z9' }).blood_type).toBeTruthy()
    expect(errorsOf({ ...valid, blood_type: 'hola' }).blood_type).toBeTruthy()
  })

  it('el teléfono admite solo números', () => {
    expect(errorsOf({ ...valid, phone: '3001112233' }).phone).toBeUndefined()
    for (const bad of ['300 111 2233', '300-111', 'abc1234567', '12']) {
      expect(errorsOf({ ...valid, phone: bad }).phone, bad).toMatch(/solo números/)
    }
  })

  it('valida formato de correo y sexo', () => {
    expect(errorsOf({ ...valid, email: 'no-es-correo' }).email).toMatch(/correo/)
    expect(errorsOf({ ...valid, sex: 'X' }).sex).toBeTruthy()
  })
})

describe('helpers', () => {
  it('digitsOnly quita todo lo que no sea número', () => {
    expect(digitsOnly('300-111 22a33')).toBe('3001112233')
  })

  it('todayISO formatea en hora local', () => {
    expect(todayISO(new Date(2026, 9, 5))).toBe('2026-10-05')
  })
})

describe('intakePatientSchema', () => {
  const base = {
    document_type: 'CC',
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

  it('exige tipo y número de documento, nombre, apellido y prioridad', () => {
    expect(intakePatientSchema.safeParse(base).success).toBe(true)
    for (const key of ['document_type', 'document_number', 'first_name', 'first_last_name', 'priority_id']) {
      expect(intakePatientSchema.safeParse({ ...base, [key]: '' }).success, key).toBe(false)
    }
  })

  it('normaliza vacíos a null y rechaza RH o fechas inválidas', () => {
    const out = intakePatientSchema.parse(base)
    expect(out.sex).toBeNull()
    expect(out.birth_date).toBeNull()
    expect(out.blood_type).toBeNull()
    expect(intakePatientSchema.safeParse({ ...base, blood_type: 'Z9' }).success).toBe(false)
    expect(intakePatientSchema.safeParse({ ...base, birth_date: '2999-01-01' }).success).toBe(false)
  })
})
