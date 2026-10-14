import { z } from 'zod'
import { zOptionalText, zRequiredEnum, zRequiredText } from '#andromeda/utils/zodFields'

const SEX = ['M', 'F'] as const

const requiredEmail = zRequiredText('El correo electrónico es obligatorio.', 255).pipe(
  z.string().email('Ingresa un correo electrónico válido.')
)

const requiredPhone = zRequiredText('El teléfono es obligatorio.', 32).pipe(
  z.string().regex(/^[0-9+()\-\s]{7,}$/, 'Ingresa un teléfono válido (mínimo 7 dígitos).')
)

const requiredBirthDate = zRequiredText('La fecha de nacimiento es obligatoria.').refine(
  // vacío ya lo cubre el mensaje de obligatorio
  (value) => !value || (!Number.isNaN(Date.parse(value)) && new Date(value) <= new Date()),
  'La fecha de nacimiento no puede ser futura.'
)

/**
 * Recepción: todos los campos son obligatorios salvo segundo nombre y segundo
 * apellido (pueden no existir). Debe coincidir con `REQUIRED_PATIENT_FIELDS`
 * del backend.
 */
export const receptionPatientSchema = z.object({
  first_name: zRequiredText('El primer nombre es obligatorio.', 80),
  second_name: zOptionalText(80),
  first_last_name: zRequiredText('El primer apellido es obligatorio.', 80),
  second_last_name: zOptionalText(80),
  birth_date: requiredBirthDate,
  birth_place: zRequiredText('El lugar de nacimiento es obligatorio.', 120),
  sex: zRequiredEnum(SEX, 'El sexo es obligatorio.'),
  blood_type: zRequiredText('El RH es obligatorio.', 3),
  email: requiredEmail,
  phone: requiredPhone,
  insurer: zRequiredText('La aseguradora es obligatoria.', 150),
  address: zRequiredText('La dirección de residencia es obligatoria.', 255)
})

/** Pre-recepción: solo la identidad que trae la cédula, más la prioridad. */
export const intakePatientSchema = z.object({
  document_number: zRequiredText('El número de documento es obligatorio.', 20),
  first_name: zRequiredText('El primer nombre es obligatorio.', 80),
  second_name: zOptionalText(80),
  first_last_name: zRequiredText('El primer apellido es obligatorio.', 80),
  second_last_name: zOptionalText(80),
  sex: z.union([z.enum(SEX), z.literal('')]).transform((v) => (v === '' ? null : v)),
  birth_date: z.string().transform((v) => (v.trim() ? v.trim() : null)),
  blood_type: z.string().transform((v) => (v.trim() ? v.trim().toUpperCase() : null)),
  priority_id: z.string({ required_error: 'Selecciona una prioridad.' }).min(1, 'Selecciona una prioridad.')
})

export type ReceptionPatientInput = z.input<typeof receptionPatientSchema>
export type IntakePatientInput = z.input<typeof intakePatientSchema>
