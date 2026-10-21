import type { LabReceptionOrder, OrderDetail, OrderSample, Patient, QueueEntry, QueueStatus } from '../types'

/** Datos de prueba (solo tests; Nuxt no auto-importa `app/testing/`). */
export const PATIENT: Patient = {
  id: 'p1',
  document_type: 'CC',
  document_number: '1001',
  first_name: 'Luisa',
  second_name: null,
  first_last_name: 'Gómez',
  second_last_name: null,
  sex: 'F',
  birth_date: '1990-05-01',
  birth_place: 'Cali',
  blood_type: 'O+',
  email: 'luisa@x.co',
  phone: '3001234567',
  address: 'Calle 1',
  insurer: null
}

export function entry(status: QueueStatus, id = 'e1', extra: Partial<QueueEntry> = {}): QueueEntry {
  return {
    id,
    status,
    claimed_by: null,
    assigned_professional_id: null,
    assigned_professional_name: null,
    arrived_at: '2026-10-20T10:00:00Z',
    draft: {},
    patient: PATIENT,
    priority: { id: 'pr1', code: 'media', name: 'Media', color_hex: '#999999', rank: 2 },
    order_number: '2610-0001',
    version: 1,
    ...extra
  }
}

export function sample(id = 's1', extra: Partial<OrderSample> = {}): OrderSample {
  return {
    id,
    sample_type_code: 'SUERO',
    name: 'Tubo rojo',
    cap_color_hex: '#cc0000',
    draw_order: 1,
    collection_instructions: null,
    required_volume_ml: 5,
    test_codes: ['GLU'],
    area_route: ['QUI'],
    labels_printed_at: null,
    collected_at: null,
    collected_by: null,
    ...extra
  }
}

export function order(samples: OrderSample[] = [sample()]): OrderDetail {
  return { order_number: '2610-0001', queue_entry_id: 'e1', tests: [{ code: 'GLU', name: 'Glucosa' }], preconditions: [], samples }
}

export function labOrder(received = false): LabReceptionOrder {
  return {
    entry_id: 'e1',
    order_number: '2610-0001',
    patient_name: 'Luisa Gómez',
    document: 'CC 1001',
    pending: received ? 0 : 1,
    samples: [
      {
        id: 's1',
        name: 'Tubo rojo',
        cap_color_hex: '#cc0000',
        test_codes: ['GLU'],
        area_route: ['QUI'],
        received_at: received ? '2026-10-20T11:00:00Z' : null,
        received_by: received ? 'Ana Pérez' : null
      }
    ]
  }
}
