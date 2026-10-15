import { z } from 'zod'
import { zOptionalText, zRequiredEnum, zRequiredText } from '#andromeda/utils/zodFields'

const SEX = ['M', 'F'] as const
export const BLOOD_TYPES = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'] as const

/** Fecha de hoy (YYYY-MM-DD) en hora local: tope de la fecha de nacimiento. */
export function todayISO(now = new Date()): string {
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** Deja solo dígitos (teléfono, documento numérico). */
export function digitsOnly(value: string): string {
  return value.replace(/\D+/g, '')
}

const requiredEmail = zRequiredText('El correo electrónico es obligatorio.', 255).pipe(
  z.string().email('Ingresa un correo electrónico válido.')
)

const requiredPhone = zRequiredText('El teléfono es obligatorio.', 15).pipe(
  z.string().regex(/^\d{7,15}$/, 'El teléfono debe tener solo números (entre 7 y 15 dígitos).')
)

const requiredBirthDate = zRequiredText('La fecha de nacimiento es obligatoria.').refine(
  // vacío ya lo cubre el mensaje de obligatorio
  (value) => !value || (!Number.isNaN(Date.parse(value)) && value <= todayISO()),
  'La fecha de nacimiento no puede ser posterior a hoy.'
)

const requiredBloodType = zRequiredEnum(BLOOD_TYPES, 'El RH es obligatorio.')

/**
 * Recepción: todos los campos son obligatorios salvo segundo nombre, segundo
 * apellido y aseguradora. Debe coincidir con `REQUIRED_PATIENT_FIELDS` del backend.
 */
export const receptionPatientSchema = z.object({
  document_type: zRequiredText('El tipo de documento es obligatorio.', 8),
  document_number: zRequiredText('El número de documento es obligatorio.', 20).pipe(
    z.string().min(3, 'El documento debe tener al menos 3 caracteres.')
  ),
  first_name: zRequiredText('El primer nombre es obligatorio.', 80),
  second_name: zOptionalText(80),
  first_last_name: zRequiredText('El primer apellido es obligatorio.', 80),
  second_last_name: zOptionalText(80),
  birth_date: requiredBirthDate,
  birth_place: zRequiredText('El lugar de nacimiento es obligatorio.', 120),
  sex: zRequiredEnum(SEX, 'El sexo es obligatorio.'),
  blood_type: requiredBloodType,
  email: requiredEmail,
  phone: requiredPhone,
  insurer: zOptionalText(150),
  address: zRequiredText('La dirección de residencia es obligatoria.', 255)
})

/** Pre-recepción: solo la identidad que trae la cédula, más la prioridad. */
export const intakePatientSchema = z.object({
  document_type: zRequiredText('El tipo de documento es obligatorio.', 8),
  document_number: zRequiredText('El número de documento es obligatorio.', 20),
  first_name: zRequiredText('El primer nombre es obligatorio.', 80),
  second_name: zOptionalText(80),
  first_last_name: zRequiredText('El primer apellido es obligatorio.', 80),
  second_last_name: zOptionalText(80),
  sex: z.union([z.enum(SEX), z.literal('')]).transform((v) => (v === '' ? null : v)),
  birth_date: z
    .string()
    .transform((v) => (v.trim() ? v.trim() : null))
    .refine((v) => v === null || v <= todayISO(), 'La fecha de nacimiento no puede ser posterior a hoy.'),
  blood_type: z.union([z.enum(BLOOD_TYPES), z.literal('')]).transform((v) => (v === '' ? null : v)),
  priority_id: z.string({ required_error: 'Selecciona una prioridad.' }).min(1, 'Selecciona una prioridad.')
})

export type ReceptionPatientInput = z.input<typeof receptionPatientSchema>
export type IntakePatientInput = z.input<typeof intakePatientSchema>
