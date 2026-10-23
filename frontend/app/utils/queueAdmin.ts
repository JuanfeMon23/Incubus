import { z } from 'zod'
import { normalizeSearchTerm } from '#andromeda/utils/search'
import { toUserMessage } from '#andromeda/utils/userMessage'
import { zRequiredNumber, zRequiredText } from '#andromeda/utils/zodFields'
import type { QueueAdminItem, QueueAdminKind } from '../types'

/** Catálogos de la pantalla «Catálogos de la cola», en el orden de las pestañas. */
export const QUEUE_ADMIN_KINDS: QueueAdminKind[] = ['priorities', 'removal-reasons', 'return-reasons']

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
  'return-reasons': { tab: 'Motivos de devolución', article: 'un', noun: 'motivo de devolución', feminine: false }
}

export const isPriorityKind = (kind: QueueAdminKind) => kind === 'priorities'

export const CODE_PATTERN = /^[a-z0-9]+([-_][a-z0-9]+)*$/
export const HEX_PATTERN = /^#[0-9A-Fa-f]{6}$/
/** Código de la prioridad por defecto de la cola: el backend no permite desactivarla. */
export const PROTECTED_PRIORITY_CODE = 'media'
export const PAGE_SIZE = 20

export interface CatalogFormInput {
  code: string
  name: string
  color_hex: string
  rank: string | number | null | undefined
}
export interface CatalogFormValues {
  code: string
  name: string
  color_hex: string
  rank: number
}

/**
 * Schema del formulario crear/editar de un catálogo. El `code` solo se valida al crear
 * (no es editable); `color_hex` y `rank` solo se exigen en prioridades.
 */
export function catalogFormSchema(opts: { priority: boolean, create: boolean }) {
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
      : z.unknown().optional()
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
  return Object.keys(body).length ? body : null
}

/** La prioridad «media» no se puede desactivar: se explica en lugar de ofrecer el botón. */
export function deactivateBlockedReason(kind: QueueAdminKind, item: Pick<QueueAdminItem, 'code' | 'is_active'>): string | null {
  if (isPriorityKind(kind) && item.code === PROTECTED_PRIORITY_CODE) {
    return 'La prioridad «Media» es la predeterminada de la cola y no se puede desactivar.'
  }
  return null
}

/** Valor para `<input type="color">` (exige #rrggbb válido). */
export function colorInputValue(hex: string | null | undefined): string {
  return hex && HEX_PATTERN.test(hex.trim()) ? hex.trim().toLowerCase() : '#000000'
}

/** Parámetros de `GET /queue-admin/{kind}`: omite `q` vacío y `is_active` indefinido. */
export function listParams(opts: { page: number, search: string, isActive: boolean | undefined }) {
  const q = normalizeSearchTerm(opts.search)
  return {
    page: opts.page,
    page_size: PAGE_SIZE,
    ...(q ? { q } : {}),
    ...(opts.isActive !== undefined ? { is_active: opts.isActive } : {})
  }
}

interface ErrorShape { status?: number, code?: string, details?: unknown }

/**
 * Mensaje legible de un error de la administración de catálogos. Los 409 de unicidad
 * (`details.field`/`value`) se explican con el campo; el del orden aclara cómo intercambiar.
 * Cualquier otro error pasa por `toUserMessage` (nunca el texto crudo).
 */
export function queueAdminErrorMessage(err: unknown, kind: QueueAdminKind): string {
  const e = (err ?? {}) as ErrorShape
  const details = (e.details ?? null) as { field?: unknown, value?: unknown } | null
  if (e.status === 409 && e.code === 'conflict' && details && typeof details.field === 'string') {
    const { noun, article } = KIND_INFO[kind]
    const value = details.value !== undefined && details.value !== null ? ` «${String(details.value)}»` : ''
    if (details.field === 'rank') {
      return `Ya existe ${article} ${noun} con el orden${value}. Para intercambiar el orden entre dos registros, primero mueve uno a un orden libre y luego asigna ese orden al otro.`
    }
    if (details.field === 'name') return `Ya existe ${article} ${noun} con el nombre${value}. Usa un nombre distinto.`
    if (details.field === 'code') return `Ya existe ${article} ${noun} con el código${value}. Usa un código distinto.`
  }
  return toUserMessage(err)
}
