export type QueueStatus =
  | 'pre_recepcion'
  | 'en_atencion_recepcion'
  | 'en_espera_impresion'
  | 'en_espera_toma_muestras'
  | 'en_atencion_toma_muestras'
  | 'toma_finalizada'
  | 'en_laboratorio'
  | 'finalizada'
  | 'retirado'

export interface Priority { id: string; code: string; name: string; color_hex: string; rank: number }
export interface Reason { id: string; code: string; name: string }
export interface Patient {
  id: string
  document_type: string
  document_number: string
  first_name: string
  second_name: string | null
  first_last_name: string
  second_last_name: string | null
  sex: 'M' | 'F' | null
  birth_date: string | null
  birth_place: string | null
  blood_type: string | null
  email: string | null
  phone: string | null
  address: string | null
  insurer: string | null
}
export interface QueueEntry {
  id: string
  status: QueueStatus
  claimed_by: string | null
  /** Id de Leo de quien tomó el turno; null en turnos legados (dueño desconocido). */
  claimed_by_user_id?: string | null
  assigned_professional_id: string | null
  assigned_professional_name: string | null
  arrived_at: string
  draft: { test_codes?: string[] }
  patient: Patient
  priority: Priority
  order_number: string | null
  version: number
}
export interface CatalogTest { code: string; name: string; abbreviation: string | null }
export interface OrderPrecondition {
  key: string
  reception_met?: boolean | null
  reception_note?: string | null
  sampling_met?: boolean | null
  sampling_note?: string | null
  category: string
  name: string
  duration_value: number | null
  duration_unit: string | null
  patient_instructions: string | null
  source_test_codes: string[]
}
export interface OrderSample {
  id: string
  sample_type_code: string
  name: string
  cap_color_hex: string | null
  draw_order: number | null
  collection_instructions: string | null
  required_volume_ml: number | null
  test_codes: string[]
  area_route: string[]
  labels_printed_at: string | null
  collected_at: string | null
  collected_by: string | null
  collected_by_user_id?: string | null
  received_by?: string | null
  received_by_user_id?: string | null
}
export interface OrderDetail {
  order_number: string
  queue_entry_id: string
  tests: { code: string; name: string }[]
  preconditions: OrderPrecondition[]
  samples: OrderSample[]
}
export interface ApiErrorBody { code?: string; message?: string; details?: unknown }

export interface StaffMember { id: string; name: string; job_title: string | null }

export interface LabReceptionSample {
  id: string
  name: string
  cap_color_hex: string | null
  test_codes: string[]
  area_route: string[]
  received_at: string | null
  received_by: string | null
}
export interface LabReceptionOrder {
  entry_id: string
  order_number: string
  patient_name: string
  document: string
  pending: number
  samples: LabReceptionSample[]
}
export interface ValidatorStaff {
  id: string
  name: string
  areas: { id: string; code: string; name: string }[]
}
export interface ResultsQueueTest {
  order_test_id: string
  code: string
  name: string
  area_code: string | null
  validation_status: 'pending' | 'draft' | 'validated'
}
export interface ResultsQueueOrder {
  entry_id: string
  order_number: string
  patient_name: string
  document: string
  tests: ResultsQueueTest[]
}
export interface ResultRow {
  code: string
  name: string
  section: string | null
  result_type: 'numeric' | 'boolean' | 'qualitative' | 'semi_quantitative' | 'titer' | 'text' | 'calculated'
  unit: string | null
  decimals: number | null
  options: { id: string; label: string }[]
  formula: string | null
  is_required: boolean
  is_reportable: boolean
  /** Quién capturó el valor (nombre) y su usuario; opcionales. */
  entered_by?: string | null
  entered_by_user_id?: string | null
  reference: string | null
  range: { low: number | null; high: number | null; critical_low: number | null; critical_high: number | null } | null
  value: string | number | boolean | null
  flag: string | null
}
export interface ResultTestDetail {
  order_test_id: string
  order_number: string
  code: string
  name: string
  area_code: string | null
  validation_status: 'pending' | 'draft' | 'validated'
  validated_by: string | null
  /** Usuario que EJECUTÓ la validación (distinto del profesional que firma, `validated_by`). */
  validated_by_user_id?: string | null
  /** Nombre de ese usuario, si el backend lo trae. */
  validated_by_user?: string | null
  patient: {
    name: string
    document_type: string
    document_number: string
    sex: string | null
    age_years: number | null
  }
  results: ResultRow[]
}

export interface OrderValidationTest {
  order_test_id: string
  code: string
  name: string
  area_code: string | null
  validation_status: 'pending' | 'draft' | 'validated'
  validated_by: string | null
  validated_by_user_id?: string | null
  validated_by_user?: string | null
  validated_at: string | null
}
export interface OrderValidationView {
  entry_id: string
  order_number: string
  patient: {
    name: string
    document_type: string
    document_number: string
    sex: string | null
    age_years: number | null
  }
  tests: OrderValidationTest[]
}

export type QueueHistoryKind = 'enter' | 'advance' | 'return' | 'remove'
/** Fila de `GET /queue/{id}/history`. */
export interface QueueHistoryRow {
  from_status: QueueStatus | null
  to_status: QueueStatus
  kind: QueueHistoryKind | string
  changed_at: string
  actor: string | null
  actor_user_id: string | null
  note: string | null
  removal_reason_id: string | null
  return_reason_id: string | null
  /** Nombre del motivo de retiro / devolución (opcional según versión del backend). */
  removal_reason_name?: string | null
  return_reason_name?: string | null
}

/** Catálogos administrables de la cola (`/queue-admin/{kind}`). */
export type QueueAdminKind = 'priorities' | 'removal-reasons' | 'return-reasons'
/** Fila de un catálogo; `color_hex` y `rank` solo vienen en prioridades. */
export interface QueueAdminItem {
  id: string
  code: string
  name: string
  is_active: boolean
  created_at: string
  updated_at: string
  color_hex: string | null
  rank: number | null
}
export interface QueueAdminPage {
  items: QueueAdminItem[]
  page: number
  page_size: number
  total: number
}

export type TraceScope = 'test' | 'order' | 'sample'
/** Evento de `GET /orders/{order_number}/tests/{test_id}/trace`. */
export interface TraceEvent {
  at: string
  step: string
  scope: TraceScope
  actor: { id: string | null; name: string | null; staff_id: string | null }
  summary: string
  details: Record<string, any>
  source: 'event' | 'derived'
}
export interface TracePage {
  order_number: string
  order_id: string
  test: { id: string; code: string; name: string; area_code: string | null; validation_status: string; created_at: string }
  events: TraceEvent[]
  page: number
  page_size: number
  total: number
}
