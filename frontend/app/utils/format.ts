import type { Patient } from '../types'

const UNIT_LABEL: Record<string, string> = { minutos: 'min', horas: 'h', dias: 'd' }

/** "12 h", "2 d"; vacío si el preanalítico no tiene duración. */
export function formatDuration(value: number | null, unit: string | null): string {
  if (value === null || value === undefined || !unit) return ''
  return `${Number.isInteger(value) ? value : value.toFixed(1)} ${UNIT_LABEL[unit] ?? unit}`
}

export function fullName(
  pick: Pick<Patient, 'first_name' | 'second_name' | 'first_last_name' | 'second_last_name'>
): string {
  return [pick.first_name, pick.second_name, pick.first_last_name, pick.second_last_name].filter(Boolean).join(' ')
}

export function ageFrom(birthDate: string | null, today = new Date()): number | null {
  if (!birthDate) return null
  const birth = new Date(`${birthDate}T00:00:00`)
  if (Number.isNaN(birth.getTime())) return null
  let age = today.getFullYear() - birth.getFullYear()
  const beforeBirthday =
    today.getMonth() < birth.getMonth() || (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate())
  if (beforeBirthday) age -= 1
  return age
}

/** `http://host:8001/api/v1` -> `http://host:8001` (origen del backend, para Socket.IO). */
export function originFromApiBase(apiBase: string): string {
  return new URL(apiBase).origin
}

export function waitingLabel(arrivedAt: string, now = Date.now()): string {
  const mins = Math.max(0, Math.floor((now - new Date(arrivedAt).getTime()) / 60000))
  return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)} h ${mins % 60} min`
}
