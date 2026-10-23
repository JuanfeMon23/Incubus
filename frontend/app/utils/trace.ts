import type { TraceEvent, TraceScope } from '../types'

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

const STEP_LABELS: Record<string, string> = {
  'order.test_added': 'Prueba agregada',
  'order.finalized': 'Orden finalizada',
  'labels.printed': 'Etiquetas impresas',
  'labels.downloaded': 'Etiquetas descargadas',
  'sample.collected': 'Tubo tomado',
  'sample.uncollected': 'Toma deshecha',
  'lab.received': 'Tubo recibido en laboratorio',
  'lab.unreceived': 'Recepción deshecha',
  'precondition.checked': 'Precondición verificada',
  'result.entered': 'Resultado capturado',
  'result.changed': 'Resultado modificado',
  'result.cleared': 'Resultado borrado',
  'test.validated': 'Prueba validada',
  'activation.issued': 'Activación emitida',
  'activation.used': 'Activación usada',
  'delivery.order_viewed': 'Orden consultada por el servicio de entrega',
  'delivery.report_downloaded': 'Informe descargado',
  'delivery.patient_orders_listed': 'Órdenes del paciente listadas',
  'queue.entered': 'Ingreso a la cola',
  'queue.reception_claimed': 'Recepción iniciada',
  'queue.reception_closed': 'Recepción cerrada',
  'queue.labels_printed': 'Etiquetas impresas (cola)',
  'queue.sampling_claimed': 'Toma de muestras iniciada',
  'queue.sampling_finished': 'Toma de muestras finalizada',
  'queue.in_laboratory': 'Paso a laboratorio',
  'queue.removed': 'Retirado de la cola',
  'queue.returned': 'Devuelto en la cola'
}

/** Categoría de un paso; los pasos nuevos o desconocidos caen en `order`. */
export function stepCategory(step: string): TraceCategory {
  const [prefix, name = ''] = step.split('.')
  switch (prefix) {
    case 'queue':
      if (name.startsWith('reception')) return 'reception'
      if (name.startsWith('sampling')) return 'sampling'
      if (name === 'labels_printed') return 'labels'
      if (name === 'in_laboratory') return 'lab'
      return 'queue'
    case 'labels': return 'labels'
    case 'sample': return 'sampling'
    case 'lab': return 'lab'
    case 'precondition': return 'sampling'
    case 'result': return 'capture'
    case 'test': return 'validation'
    case 'delivery': return 'delivery'
    case 'activation': return 'activation'
    default: return 'order'
  }
}

/** Los pasos de cola (todos los `queue.*`) que el filtro «ocultar cola» esconde. */
export const isQueueStep = (step: string) => step.startsWith('queue.')

export function stepLabel(step: string): string {
  return STEP_LABELS[step] ?? step
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
  return events.filter((e) => filters.scopes.includes(e.scope) && !(filters.hideQueue && isQueueStep(e.step)))
}

export interface TraceDay {
  /** `AAAA-MM-DD` en hora local. */
  key: string
  label: string
  events: TraceEvent[]
}

const pad = (n: number) => String(n).padStart(2, '0')

export function dayKey(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function dayLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'Fecha desconocida'
  return d.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
}

/** Hora local `HH:MM:SS`. */
export function timeLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** Agrupa por día local conservando el orden recibido (cronológico). */
export function groupByDay(events: TraceEvent[]): TraceDay[] {
  const days: TraceDay[] = []
  for (const e of events) {
    const key = dayKey(e.at)
    let day = days[days.length - 1]
    if (!day || day.key !== key) {
      day = { key, label: dayLabel(e.at), events: [] }
      days.push(day)
    }
    day.events.push(e)
  }
  return days
}

const STAGE_LABELS: Record<string, string> = {
  reception: 'Recepción',
  sampling: 'Toma de muestras'
}

const show = (v: unknown): string => (v === null || v === undefined || v === '' ? '—' : String(v))
const flagText = (flag: unknown) => (flag ? ` (bandera ${flag})` : '')

function metText(c: { met?: boolean | null; note?: string | null } | null | undefined): string {
  if (!c || c.met === null || c.met === undefined) return 'Sin registrar'
  return `${c.met ? 'Cumplida' : 'No cumplida'}${c.note ? ` — ${c.note}` : ''}`
}

/** Líneas legibles de los `details` de un evento (vacío si no hay nada que mostrar). */
export function detailLines(event: Pick<TraceEvent, 'step' | 'details'>): string[] {
  const d = event.details ?? {}
  if (event.step.startsWith('result.')) {
    if (!d.analyte_code && d.before === undefined && d.after === undefined) return []
    const calc = d.calculated ? ' · calculado' : ''
    return [`${show(d.analyte_code)}: ${show(d.before)} → ${show(d.after)}${flagText(d.flag)}${calc}`]
  }
  if (event.step === 'precondition.checked') {
    const stage = STAGE_LABELS[d.stage as string] ?? (d.stage ? String(d.stage) : '')
    if (d.key || d.name) {
      const head = `${d.name || d.key}${stage ? ` (${stage})` : ''}`
      return [`${head}: ${metText(d.before)} → ${metText(d.after)}`]
    }
    const lines = [`${stage ? `${stage}: ` : ''}${d.checked ?? 0} verificadas`]
    const unmet = Array.isArray(d.unmet_keys) ? d.unmet_keys : []
    lines.push(unmet.length ? `No cumplidas: ${unmet.join(', ')}` : 'Todas cumplidas')
    return lines
  }
  if (event.step === 'test.validated') {
    const flags = Array.isArray(d.abnormal_flags) ? d.abnormal_flags : []
    const lines = [
      flags.length
        ? `Banderas anormales: ${flags.map((f: { analyte_code: string; flag: string }) => `${f.analyte_code} ${f.flag}`).join(', ')}`
        : 'Sin banderas anormales'
    ]
    if (d.validated_by) lines.push(`Firmado por: ${d.validated_by}`)
    return lines
  }
  return []
}
