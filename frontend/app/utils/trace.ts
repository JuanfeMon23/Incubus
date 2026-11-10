import type { TraceEvent, TraceScope, TraceStepCatalogItem } from '../types'

/** Categorías visuales de la línea de tiempo de una prueba. */
export type TraceCategory =
  | 'order' | 'queue' | 'reception' | 'labels' | 'sampling' | 'lab' | 'capture' | 'validation' | 'delivery' | 'activation'

export interface CategoryInfo {
  label: string
  /** Clase de fondo del punto/icono. */
  dot: string
  /** Trazo 24×24 (atributo `d`). */
  icon: string
}

export const CATEGORY_INFO: Record<TraceCategory, CategoryInfo> = {
  order: { label: 'Orden', dot: 'bg-default-500', icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 12h6M9 16h4' },
  queue: { label: 'Cola', dot: 'bg-default-400', icon: 'M4 6h16M4 12h16M4 18h10' },
  reception: { label: 'Recepción', dot: 'bg-primary-500', icon: 'M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.5 20.118a7.5 7.5 0 0 1 15 0' },
  labels: { label: 'Etiquetas', dot: 'bg-secondary-500', icon: 'M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v7H6v-7Z' },
  sampling: { label: 'Toma de muestra', dot: 'bg-danger-500', icon: 'M12 2.5s6 6.2 6 10.5a6 6 0 0 1-12 0C6 8.7 12 2.5 12 2.5Z' },
  lab: { label: 'Laboratorio', dot: 'bg-warning-500', icon: 'M4 13h4l1 3h6l1-3h4M4 13V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7M4 13v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5' },
  capture: { label: 'Captura', dot: 'bg-primary-600', icon: 'M4 20h4L19 9l-4-4L4 16v4ZM13.5 6.5l4 4' },
  validation: { label: 'Validación', dot: 'bg-success-500', icon: 'M5 12.5l4.5 4.5L19 7.5' },
  delivery: { label: 'Entrega', dot: 'bg-success-600', icon: 'M12 3v12m0 0l-4-4m4 4l4-4M4 20h16' },
  activation: { label: 'Activación', dot: 'bg-secondary-600', icon: 'M15 7a4 4 0 1 1-3.9 4.9L4 19v-3l2-2h2v-2h2l1.1-1.1A4 4 0 0 1 15 7Z' }
}

/** Categoría de un paso según `trace-steps`; un paso nuevo o desconocido cae en `order`. */
export function stepCategory(step: string, steps: readonly TraceStepCatalogItem[] = []): TraceCategory {
  const category = steps.find((item) => item.code === step)?.category
  return category && category in CATEGORY_INFO ? (category as TraceCategory) : 'order'
}

/** Los pasos de cola (todos los `queue.*`) que el filtro «ocultar cola» esconde. */
export const isQueueStep = (step: string) => step.startsWith('queue.')

/** Nombre del paso según `trace-steps`; sin coincidencia, el code. */
export function stepLabel(step: string, steps: readonly TraceStepCatalogItem[] = []): string {
  return steps.find((item) => item.code === step)?.name ?? step
}

export const SCOPE_LABELS: Record<TraceScope, string> = { test: 'Prueba', order: 'Orden', sample: 'Tubo' }
export const SCOPES: TraceScope[] = ['test', 'order', 'sample']

/** Nombre legible del actor: sin nombre (sistema o cliente de servicio) -> «Sistema/servicio». */
export function actorName(actor: TraceEvent['actor'] | null | undefined): string {
  return actor?.name?.trim() || 'Sistema/servicio'
}

export interface TraceFilters {
  scopes: TraceScope[]
  hideQueue: boolean
}

export function filterEvents(events: TraceEvent[], filters: TraceFilters): TraceEvent[] {
  return events.filter((event) => filters.scopes.includes(event.scope) && !(filters.hideQueue && isQueueStep(event.step)))
}

export interface TraceDay {
  /** `AAAA-MM-DD` en hora local. */
  key: string
  label: string
  events: TraceEvent[]
}

const pad = (value: number) => String(value).padStart(2, '0')

export function dayKey(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function dayLabel(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'Fecha desconocida'
  return date.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
}

/** Hora local `HH:MM:SS`. */
export function timeLabel(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

/** Agrupa por día local conservando el orden recibido (cronológico). */
export function groupByDay(events: TraceEvent[]): TraceDay[] {
  const days: TraceDay[] = []
  for (const event of events) {
    const key = dayKey(event.at)
    let day = days[days.length - 1]
    if (!day || day.key !== key) {
      day = { key, label: dayLabel(event.at), events: [] }
      days.push(day)
    }
    day.events.push(event)
  }
  return days
}

const STAGE_LABELS: Record<string, string> = {
  reception: 'Recepción',
  sampling: 'Toma de muestras'
}

const show = (value: unknown): string => (value === null || value === undefined || value === '' ? '—' : String(value))
const flagText = (flag: unknown) => (flag ? ` (bandera ${flag})` : '')

function metText(check: { met?: boolean | null; note?: string | null } | null | undefined): string {
  if (!check || check.met === null || check.met === undefined) return 'Sin registrar'
  return `${check.met ? 'Cumplida' : 'No cumplida'}${check.note ? ` — ${check.note}` : ''}`
}

/** Líneas legibles de los `details` de un evento (vacío si no hay nada que mostrar). */
export function detailLines(event: Pick<TraceEvent, 'step' | 'details'>): string[] {
  const details = event.details ?? {}
  if (event.step.startsWith('result.')) {
    if (!details.analyte_code && details.before === undefined && details.after === undefined) return []
    const calc = details.calculated ? ' · calculado' : ''
    return [`${show(details.analyte_code)}: ${show(details.before)} → ${show(details.after)}${flagText(details.flag)}${calc}`]
  }
  if (event.step === 'precondition.checked') {
    const stage = STAGE_LABELS[details.stage as string] ?? (details.stage ? String(details.stage) : '')
    if (details.key || details.name) {
      const head = `${details.name || details.key}${stage ? ` (${stage})` : ''}`
      return [`${head}: ${metText(details.before)} → ${metText(details.after)}`]
    }
    const lines = [`${stage ? `${stage}: ` : ''}${details.checked ?? 0} verificadas`]
    const unmet = Array.isArray(details.unmet_keys) ? details.unmet_keys : []
    lines.push(unmet.length ? `No cumplidas: ${unmet.join(', ')}` : 'Todas cumplidas')
    return lines
  }
  if (event.step === 'test.validated') {
    const flags = Array.isArray(details.abnormal_flags) ? details.abnormal_flags : []
    const lines = [
      flags.length
        ? `Banderas anormales: ${flags.map((abnormal: { analyte_code: string; flag: string }) => `${abnormal.analyte_code} ${abnormal.flag}`).join(', ')}`
        : 'Sin banderas anormales'
    ]
    if (details.validated_by) lines.push(`Firmado por: ${details.validated_by}`)
    return lines
  }
  return []
}
