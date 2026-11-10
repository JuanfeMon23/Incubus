import { z } from 'zod'
import { normalizeSearchTerm } from '#andromeda/utils/search'
import { leoErrorMessage } from '#leo-client/lib/errors'
import { zRequiredNumber, zRequiredText } from '#andromeda/utils/zodFields'
import type { QueueAdminItem, QueueAdminKind } from '../types'

/** Catálogos de la pantalla «Catálogos de la cola», en el orden de las pestañas. */
export const QUEUE_ADMIN_KINDS: QueueAdminKind[] = [
  'priorities', 'removal-reasons', 'return-reasons',
  'blood-types', 'queue-statuses', 'queue-transition-kinds', 'validation-statuses', 'result-flags', 'trace-steps'
]

/**
 * Catálogos de sistema: sus codes los usa la lógica, así que solo se edita nombre, orden y
 * presentación (nada se crea ni se activa/desactiva: el backend responde 409).
 */
const SYSTEM_KINDS: readonly QueueAdminKind[] = ['blood-types', 'queue-statuses', 'queue-transition-kinds', 'validation-statuses', 'result-flags', 'trace-steps']
export const isSystemKind = (kind: QueueAdminKind) => SYSTEM_KINDS.includes(kind)
export const isResultFlagKind = (kind: QueueAdminKind) => kind === 'result-flags'

/** Variantes de color de una bandera de resultado (`variant` de `result-flags`). */
export const FLAG_VARIANT_OPTIONS = [
  { value: 'success', label: 'Éxito (verde)' },
  { value: 'warning', label: 'Advertencia (amarillo)' },
  { value: 'danger', label: 'Peligro (rojo)' }
]

interface KindInfo {
  /** Título de la pestaña. */
  tab: string
  /** «una prioridad», «un motivo de retiro»… (concordancia en los mensajes). */
  article: string
  noun: string
  /** Género para «Nueva / Nuevo», «Desactivar la / el». */
  feminine: boolean
}

export const KIND_INFO: Record<QueueAdminKind, KindInfo> = {
  priorities: { tab: 'Prioridades', article: 'una', noun: 'prioridad', feminine: true },
  'removal-reasons': { tab: 'Motivos de retiro', article: 'un', noun: 'motivo de retiro', feminine: false },
  'return-reasons': { tab: 'Motivos de devolución', article: 'un', noun: 'motivo de devolución', feminine: false },
  'blood-types': { tab: 'Tipos de sangre', article: 'un', noun: 'tipo de sangre', feminine: false },
  'queue-statuses': { tab: 'Estados de la cola', article: 'un', noun: 'estado de la cola', feminine: false },
  'queue-transition-kinds': { tab: 'Tipos de transición', article: 'un', noun: 'tipo de transición', feminine: false },
  'validation-statuses': { tab: 'Estados de validación', article: 'un', noun: 'estado de validación', feminine: false },
  'result-flags': { tab: 'Banderas de resultado', article: 'una', noun: 'bandera de resultado', feminine: true },
  'trace-steps': { tab: 'Pasos de trazabilidad', article: 'un', noun: 'paso de trazabilidad', feminine: false }
}

export const isPriorityKind = (kind: QueueAdminKind) => kind === 'priorities'

export const CODE_PATTERN = /^[a-z0-9]+([-_][a-z0-9]+)*$/
export const HEX_PATTERN = /^#[0-9A-Fa-f]{6}$/
export const PAGE_SIZE = 20

export interface CatalogFormInput {
  code: string
  name: string
  color_hex: string
  rank: string | number | null | undefined
  sort_order?: string | number | null
  variant?: string
  show_in_report?: boolean
}
export interface CatalogFormValues {
  code: string
  name: string
  color_hex: string
  rank: number
  sort_order?: number
  variant?: 'success' | 'warning' | 'danger'
  show_in_report?: boolean
}

/**
 * Schema del formulario crear/editar de un catálogo. El `code` solo se valida al crear
 * (no es editable); `color_hex` y `rank` solo se exigen en prioridades.
 */
export function catalogFormSchema(opts: { priority: boolean, create: boolean, system?: boolean, resultFlag?: boolean }) {
  const schema = z.object({
    code: opts.create
      ? zRequiredText('El código es obligatorio.', 64).regex(
        CODE_PATTERN,
        'Usa minúsculas, números y guiones (-, _) entre grupos; por ejemplo «sin-datos».'
      )
      : z.string().optional(),
    name: zRequiredText('El nombre es obligatorio.', 255),
    color_hex: opts.priority
      ? z.string({ required_error: 'El color es obligatorio.' }).trim().regex(HEX_PATTERN, 'Ingresa el color como #RRGGBB, por ejemplo #FF8800.')
      : z.string().optional(),
    rank: opts.priority
      ? zRequiredNumber('El orden es obligatorio.', { integer: true, min: 1 })
      : z.unknown().optional(),
    sort_order: opts.system
      ? zRequiredNumber('El orden es obligatorio.', { integer: true, min: 0 })
      : z.unknown().optional(),
    variant: opts.resultFlag
      ? z.enum(['success', 'warning', 'danger'], { errorMap: () => ({ message: 'Selecciona una variante.' }) })
      : z.unknown().optional(),
    show_in_report: opts.resultFlag ? z.boolean() : z.unknown().optional()
  })
  return schema as unknown as z.ZodType<CatalogFormValues, z.ZodTypeDef, CatalogFormInput>
}

/** Motivo obligatorio al desactivar. */
export const deactivateSchema = z.object({
  reason: zRequiredText('El motivo es obligatorio.', 255)
})

/** Cuerpo del POST de creación. */
export function buildCreatePayload(kind: QueueAdminKind, values: CatalogFormValues) {
  const body: Record<string, unknown> = { code: values.code, name: values.name }
  if (isPriorityKind(kind)) {
    body.color_hex = values.color_hex.toUpperCase()
    body.rank = values.rank
  }
  return body
}

/** Cuerpo del PATCH: solo lo que cambió (sin cambios el backend responde 422). `null`: nada que enviar. */
export function buildUpdatePayload(kind: QueueAdminKind, values: CatalogFormValues, item: QueueAdminItem) {
  const body: Record<string, unknown> = {}
  if (values.name !== item.name) body.name = values.name
  if (isPriorityKind(kind)) {
    const color = values.color_hex.toUpperCase()
    if (color !== (item.color_hex ?? '').toUpperCase()) body.color_hex = color
    if (values.rank !== item.rank) body.rank = values.rank
  }
  if (isSystemKind(kind)) {
    if (values.sort_order !== item.sort_order) body.sort_order = values.sort_order
    if (isResultFlagKind(kind)) {
      if (values.variant !== item.variant) body.variant = values.variant
      if (values.show_in_report !== item.show_in_report) body.show_in_report = values.show_in_report
    }
  }
  return Object.keys(body).length ? body : null
}

/** La prioridad por defecto no se puede desactivar: se explica en lugar de ofrecer el botón. */
export function deactivateBlockedReason(kind: QueueAdminKind, item: Pick<QueueAdminItem, 'is_default'>): string | null {
  if (isPriorityKind(kind) && item.is_default === true) {
    return 'Es la prioridad predeterminada de la cola y no se puede desactivar. Haz predeterminada otra prioridad primero.'
  }
  return null
}

/** «Hacer predeterminada» solo aplica a una prioridad activa que aún no lo es. */
export function canMakeDefault(kind: QueueAdminKind, item: Pick<QueueAdminItem, 'is_active' | 'is_default'>): boolean {
  return isPriorityKind(kind) && item.is_active && item.is_default !== true
}

/** Motivo opcional al cambiar la predeterminada: se omite si queda vacío. */
export const setDefaultSchema = z.object({
  reason: z.string().trim().max(255, 'Máximo 255 caracteres.').optional()
})

/** Valor para `<input type="color">` (exige #rrggbb válido). */
export function colorInputValue(hex: string | null | undefined): string {
  return hex && HEX_PATTERN.test(hex.trim()) ? hex.trim().toLowerCase() : '#000000'
}

/** Parámetros de `GET /queue-admin/{kind}`: omite `q` vacío y `is_active` indefinido. */
export function listParams(opts: { page: number, search: string, isActive: boolean | undefined }) {
  const term = normalizeSearchTerm(opts.search)
  return {
    page: opts.page,
    page_size: PAGE_SIZE,
    ...(term ? { q: term } : {}),
    ...(opts.isActive !== undefined ? { is_active: opts.isActive } : {})
  }
}

interface ErrorShape { status?: number, code?: string, details?: unknown }

/**
 * Mensaje legible de un error de la administración de catálogos. Los 409 de unicidad
 * (`details.field`/`value`) se explican con el campo; el del orden aclara cómo intercambiar.
 * Cualquier otro error pasa por `leoErrorMessage` (nunca el texto crudo).
 */
export function queueAdminErrorMessage(err: unknown, kind: QueueAdminKind): string {
  const errorShape = (err ?? {}) as ErrorShape
  const details = (errorShape.details ?? null) as { field?: unknown, value?: unknown } | null
  if (errorShape.status === 409 && errorShape.code === 'conflict' && details && typeof details.field === 'string') {
    const { noun, article } = KIND_INFO[kind]
    const value = details.value !== undefined && details.value !== null ? ` «${String(details.value)}»` : ''
    if (details.field === 'rank' || details.field === 'sort_order') {
      return `Ya existe ${article} ${noun} con el orden${value}. Para intercambiar el orden entre dos registros, primero mueve uno a un orden libre y luego asigna ese orden al otro.`
    }
    if (details.field === 'name') return `Ya existe ${article} ${noun} con el nombre${value}. Usa un nombre distinto.`
    if (details.field === 'code') return `Ya existe ${article} ${noun} con el código${value}. Usa un código distinto.`
  }
  return leoErrorMessage(err)
}
