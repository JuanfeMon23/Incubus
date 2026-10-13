import type { Patient } from '../types'

const UNIT_LABEL: Record<string, string> = { minutos: 'min', horas: 'h', dias: 'd' }

/** "12 h", "2 d"; vacío si el preanalítico no tiene duración. */
export function formatDuration(value: number | null, unit: string | null): string {
  if (value === null || value === undefined || !unit) return ''
  return `${Number.isInteger(value) ? value : value.toFixed(1)} ${UNIT_LABEL[unit] ?? unit}`
}

export function fullName(
  p: Pick<Patient, 'first_name' | 'second_name' | 'first_last_name' | 'second_last_name'>
): string {
  return [p.first_name, p.second_name, p.first_last_name, p.second_last_name].filter(Boolean).join(' ')
}

export function ageFrom(birthDate: string | null, today = new Date()): number | null {
  if (!birthDate) return null
  const b = new Date(`${birthDate}T00:00:00`)
  if (Number.isNaN(b.getTime())) return null
  let age = today.getFullYear() - b.getFullYear()
  const beforeBirthday =
    today.getMonth() < b.getMonth() || (today.getMonth() === b.getMonth() && today.getDate() < b.getDate())
  if (beforeBirthday) age -= 1
  return age
}

/** `http://host/api/v1` -> `ws://host/ws/queue`. */
export function wsUrlFromApiBase(apiBase: string): string {
  const u = new URL(apiBase)
  const proto = u.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${u.host}/ws/queue`
}

export function waitingLabel(arrivedAt: string, now = Date.now()): string {
  const mins = Math.max(0, Math.floor((now - new Date(arrivedAt).getTime()) / 60000))
  return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)} h ${mins % 60} min`
}
