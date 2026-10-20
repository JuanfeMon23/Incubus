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
