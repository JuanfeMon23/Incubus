import { z } from 'zod'
import { zOptionalText, zRequiredText } from '#andromeda/utils/zodFields'

// Sexo y RH son catálogos de BD (`sexes`, `blood-types`): aquí solo se exige que haya un code;
// el backend valida que exista y un 422 se muestra en el campo.

/** Fecha de hoy (YYYY-MM-DD) en hora local: tope de la fecha de nacimiento. */
export function todayISO(now = new Date()): string {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
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

const requiredBloodType = zRequiredText('El RH es obligatorio.', 8)

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
  sex: zRequiredText('El sexo es obligatorio.', 16),
  blood_type: requiredBloodType,
  email: requiredEmail,
  phone: requiredPhone,
  insurer: zOptionalText(150),
  address: zRequiredText('La dirección de residencia es obligatoria.', 255)
})

/** Code de catálogo opcional: vacío -> `null`. */
const optionalCode = (max: number) =>
  z.string().max(max).transform((value) => (value.trim() ? value.trim() : null))

/** Pre-recepción: solo la identidad que trae la cédula, más la prioridad. */
export const intakePatientSchema = z.object({
  document_type: zRequiredText('El tipo de documento es obligatorio.', 8),
  document_number: zRequiredText('El número de documento es obligatorio.', 20),
  first_name: zRequiredText('El primer nombre es obligatorio.', 80),
  second_name: zOptionalText(80),
  first_last_name: zRequiredText('El primer apellido es obligatorio.', 80),
  second_last_name: zOptionalText(80),
  sex: optionalCode(16),
  birth_date: z
    .string()
    .transform((value) => (value.trim() ? value.trim() : null))
    .refine((value) => value === null || value <= todayISO(), 'La fecha de nacimiento no puede ser posterior a hoy.'),
  blood_type: optionalCode(8),
  priority_id: z.string({ required_error: 'Selecciona una prioridad.' }).min(1, 'Selecciona una prioridad.')
})

export type ReceptionPatientInput = z.input<typeof receptionPatientSchema>
export type IntakePatientInput = z.input<typeof intakePatientSchema>
