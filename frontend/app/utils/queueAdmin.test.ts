import { describe, expect, it } from 'vitest'
import type { QueueAdminItem } from '../types'
import {
  buildCreatePayload,
  buildUpdatePayload,
  canMakeDefault,
  catalogFormSchema,
  colorInputValue,
  deactivateBlockedReason,
  deactivateSchema,
  listParams,
  queueAdminErrorMessage,
  setDefaultSchema
} from './queueAdmin'
import { LeoApiError } from '#leo-client/lib/errors'

const item = (over: Partial<QueueAdminItem> = {}): QueueAdminItem => ({
  id: 'p1', code: 'urgente', name: 'Urgente', is_active: true,
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  color_hex: '#FF0000', rank: 2, is_default: false, ...over
})

describe('schema de creación', () => {
  const prio = catalogFormSchema({ priority: true, create: true })
  const reason = catalogFormSchema({ priority: false, create: true })

  it('acepta una prioridad válida y convierte el orden a número', () => {
    const r = prio.safeParse({ code: 'sin-datos', name: ' Sin datos ', color_hex: '#a1B2c3', rank: '5' })
    expect(r.success && r.data).toMatchObject({ code: 'sin-datos', name: 'Sin datos', rank: 5 })
  })

  it.each(['Urgente', 'a b', '-a', 'a--b', 'a_', 'ñandú', ''])('rechaza el code %j', (code) => {
    expect(prio.safeParse({ code, name: 'x', color_hex: '#000000', rank: 1 }).success).toBe(false)
  })

  it.each(['a_b', 'a-b-c', 'abc123'])('acepta el code %j', (code) => {
    expect(reason.safeParse({ code, name: 'x', color_hex: '', rank: '' }).success).toBe(true)
  })

  it.each(['red', '#FFF', '#GGGGGG', '#12345', '', '#1234567'])('rechaza el color %j', (color_hex) => {
    expect(prio.safeParse({ code: 'a', name: 'x', color_hex, rank: 1 }).success).toBe(false)
  })

  it.each(['', 'x', '1.5', '-1'])('rechaza el orden %j', (rank) => {
    expect(prio.safeParse({ code: 'a', name: 'x', color_hex: '#000000', rank }).success).toBe(false)
  })

  it('en motivos no exige color ni orden', () => {
    expect(reason.safeParse({ code: 'a', name: 'Motivo', color_hex: '', rank: '' }).success).toBe(true)
  })

  it('el nombre es obligatorio', () => {
    expect(reason.safeParse({ code: 'a', name: '  ', color_hex: '', rank: '' }).success).toBe(false)
  })

  it('al editar el code no se valida', () => {
    const edit = catalogFormSchema({ priority: false, create: false })
    expect(edit.safeParse({ code: 'MAL CODE', name: 'x', color_hex: '', rank: '' }).success).toBe(true)
  })
})

describe('desactivar', () => {
  it('exige motivo', () => {
    expect(deactivateSchema.safeParse({ reason: '   ' }).success).toBe(false)
    expect(deactivateSchema.safeParse({ reason: 'Ya no se usa' }).success).toBe(true)
  })

  it('la prioridad por defecto está bloqueada con explicación (aunque no se llame «media»); otras no', () => {
    expect(deactivateBlockedReason('priorities', item({ code: 'normal', is_default: true }))).toMatch(/predeterminada/)
    expect(deactivateBlockedReason('priorities', item({ code: 'media' }))).toBeNull()
    expect(deactivateBlockedReason('priorities', item())).toBeNull()
    expect(deactivateBlockedReason('removal-reasons', item({ is_default: null }))).toBeNull()
  })
})

describe('hacer predeterminada', () => {
  it('solo una prioridad activa que no lo es ya', () => {
    expect(canMakeDefault('priorities', item())).toBe(true)
    expect(canMakeDefault('priorities', item({ is_active: false }))).toBe(false)
    expect(canMakeDefault('priorities', item({ is_default: true }))).toBe(false)
    expect(canMakeDefault('removal-reasons', item({ is_default: null }))).toBe(false)
  })

  it('el motivo es opcional pero acotado', () => {
    expect(setDefaultSchema.safeParse({ reason: '' }).success).toBe(true)
    expect(setDefaultSchema.safeParse({}).success).toBe(true)
    expect(setDefaultSchema.safeParse({ reason: 'x'.repeat(256) }).success).toBe(false)
  })
})

describe('payloads', () => {
  it('creación de prioridad lleva color (mayúsculas) y orden; la de motivo solo code y name', () => {
    const v = { code: 'a', name: 'A', color_hex: '#abcdef', rank: 3 }
    expect(buildCreatePayload('priorities', v)).toEqual({ code: 'a', name: 'A', color_hex: '#ABCDEF', rank: 3 })
    expect(buildCreatePayload('return-reasons', v)).toEqual({ code: 'a', name: 'A' })
  })

  it('el PATCH envía solo lo cambiado y nunca el code', () => {
    const v = { code: 'urgente', name: 'Urgente 2', color_hex: '#ff0000', rank: 2 }
    expect(buildUpdatePayload('priorities', v, item())).toEqual({ name: 'Urgente 2' })
    expect(buildUpdatePayload('priorities', { ...v, name: 'Urgente', rank: 7 }, item())).toEqual({ rank: 7 })
  })

  it('sin cambios no hay PATCH (el backend respondería 422)', () => {
    expect(buildUpdatePayload('priorities', { code: 'urgente', name: 'Urgente', color_hex: '#ff0000', rank: 2 }, item())).toBeNull()
  })
})

describe('utilidades', () => {
  it('listParams omite q vacío e is_active indefinido', () => {
    expect(listParams({ page: 2, search: '  ', isActive: undefined })).toEqual({ page: 2, page_size: 20 })
    expect(listParams({ page: 1, search: ' alta  prio ', isActive: false })).toEqual({ page: 1, page_size: 20, q: 'alta prio', is_active: false })
  })

  it('colorInputValue cae a negro si el valor no es #RRGGBB', () => {
    expect(colorInputValue('#AABBCC')).toBe('#aabbcc')
    expect(colorInputValue('rojo')).toBe('#000000')
    expect(colorInputValue(null)).toBe('#000000')
  })
})

describe('mensajes de error', () => {
  const conflict = (field: string, value?: unknown) => ({ status: 409, code: 'conflict', message: 'crudo', details: { field, value } })

  it('orden repetido explica el intercambio', () => {
    const m = queueAdminErrorMessage(conflict('rank', 3), 'priorities')
    expect(m).toContain('orden «3»')
    expect(m).toContain('orden libre')
  })

  it('nombre y code repetidos, con el valor', () => {
    expect(queueAdminErrorMessage(conflict('name', 'Alta'), 'removal-reasons')).toBe('Ya existe un motivo de retiro con el nombre «Alta». Usa un nombre distinto.')
    expect(queueAdminErrorMessage(conflict('code', 'alta'), 'priorities')).toContain('código «alta»')
  })

  it('otros 409 usan el mensaje del backend; la red, un texto legible', () => {
    const e = { status: 409, code: 'conflict', message: 'No se puede desactivar la última prioridad activa.', data: { code: 'conflict', message: 'No se puede desactivar la última prioridad activa.' } }
    expect(queueAdminErrorMessage(e, 'priorities')).toBe('No se puede desactivar la última prioridad activa.')
    expect(queueAdminErrorMessage(new TypeError('Failed to fetch'), 'priorities')).not.toMatch(/fetch/i)
  })
})

describe('tope de page_size (ajuste del backend)', () => {
  const tooBig = (details: unknown) => new LeoApiError(422, 'validation_error', 'El tamaño de página máximo permitido es 50.', details)

  it('el 422 sobre page_size llega legible (mensaje del servidor con el máximo vigente)', () => {
    expect(queueAdminErrorMessage(tooBig({ field: 'page_size', max: 50 }), 'priorities')).toBe('El tamaño de página máximo permitido es 50.')
  })
})
