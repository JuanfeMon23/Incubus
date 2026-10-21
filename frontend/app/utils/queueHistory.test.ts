import { describe, expect, it } from 'vitest'
import type { QueueHistoryRow } from '../types'
import { actionLabel, actorLabel, historyItems, stageName } from './queueHistory'

const row = (extra: Partial<QueueHistoryRow> = {}): QueueHistoryRow => ({
  from_status: 'pre_recepcion',
  to_status: 'en_atencion_recepcion',
  kind: 'advance',
  changed_at: '2026-10-20T15:30:00Z',
  actor: 'Ana Pérez',
  actor_user_id: 'u1',
  note: null,
  removal_reason_id: null,
  return_reason_id: null,
  ...extra
})

describe('etiquetas', () => {
  it('nombra las etapas legiblemente', () => {
    expect(stageName('en_espera_toma_muestras')).toBe('Espera de toma de muestras')
    expect(stageName(null)).toBe('')
  })
  it('traduce el tipo de acción', () => {
    expect(actionLabel('enter')).toBe('Ingreso a la cola')
    expect(actionLabel('advance')).toBe('Avance')
    expect(actionLabel('return')).toBe('Devolución')
    expect(actionLabel('remove')).toBe('Retiro')
    expect(actionLabel('otra')).toBe('Cambio de estado')
  })
})

describe('actorLabel', () => {
  it('"Tú" si es el usuario actual', () => {
    expect(actorLabel(row(), 'u1')).toBe('Tú')
  })
  it('el nombre si es otra persona', () => {
    expect(actorLabel(row(), 'u2')).toBe('Ana Pérez')
  })
  it('sin id de usuario (registro antiguo) usa el nombre', () => {
    expect(actorLabel(row({ actor_user_id: null }), 'u1')).toBe('Ana Pérez')
  })
  it('sin actor dice "Sin registro"; sin sesión no dice Tú', () => {
    expect(actorLabel(row({ actor: null, actor_user_id: null }), 'u1')).toBe('Sin registro')
    expect(actorLabel(row(), undefined)).toBe('Ana Pérez')
  })
})

describe('historyItems', () => {
  it('arma líneas con acción, tránsito, motivo y quién', () => {
    const [item] = historyItems([row({ kind: 'return', note: 'Falta ayuno' })], 'u1')
    expect(item).toMatchObject({
      action: 'Devolución',
      transition: 'Pre-recepción → En atención de recepción',
      note: 'Falta ayuno',
      who: 'Tú'
    })
    expect(item!.when).toMatch(/2026/)
  })
  it('el ingreso no tiene estado de origen', () => {
    const [item] = historyItems([row({ from_status: null, kind: 'enter', to_status: 'pre_recepcion' })], 'u9')
    expect(item!.transition).toBe('Pre-recepción')
  })
  it('lista vacía', () => {
    expect(historyItems([], 'u1')).toEqual([])
  })
})

describe('motivo del retiro / devolución', () => {
  it('muestra el nombre del motivo y la nota', () => {
    const i = historyItems([row({ kind: 'return', return_reason_id: 'r1', return_reason_name: 'Sin ayuno', note: 'Comió a las 8' })], 'u9')[0]!
    expect(i.reason).toBe('Sin ayuno')
    expect(i.note).toBe('Comió a las 8')
  })
  it('motivo de retiro', () => {
    const i = historyItems([row({ kind: 'remove', removal_reason_id: 'x', removal_reason_name: 'Se fue' })], 'u9')[0]!
    expect(i.reason).toBe('Se fue')
    expect(i.note).toBeNull()
  })
  it('sin nombre cae a la nota y nunca muestra ids', () => {
    const i = historyItems([row({ kind: 'return', return_reason_id: 'r-123', note: 'Paciente sin ayuno' })], 'u9')[0]!
    expect(i.reason).toBeNull()
    expect(i.note).toBe('Paciente sin ayuno')
    expect(JSON.stringify(i)).not.toContain('r-123')
  })
})
