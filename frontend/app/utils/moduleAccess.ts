import type { QueueStatus } from '../types'
import { TAGS } from './tags'

/** Etapa (estado de la cola) -> permiso `view` de la pantalla que la muestra (espejo de `STAGE_VIEW` del backend). */
export const STAGE_VIEW_TAG: Record<QueueStatus, string> = {
  pre_recepcion: TAGS.preReception.view,
  en_atencion_recepcion: TAGS.reception.view,
  en_espera_impresion: TAGS.labelPrinting.view,
  en_espera_toma_muestras: TAGS.sampling.view,
  en_atencion_toma_muestras: TAGS.sampling.view,
  toma_finalizada: TAGS.labReception.view,
  en_laboratorio: TAGS.results.view,
  finalizada: TAGS.results.view,
  retirado: TAGS.reception.view
}

export type CanFn = (tag: string) => boolean

/** Etapas de `statuses` cuyo `view` tiene el usuario (el servidor rechaza todo el pedido si falta una). */
export function stagesWithView(statuses: QueueStatus[], can: CanFn): QueueStatus[] {
  return statuses.filter((status) => can(STAGE_VIEW_TAG[status]))
}

/** Pantallas del menú lateral; cada una exige el `view` de su etapa. */
export interface ScreenItem {
  label: string
  to: string
  tag: string
  section: string
  /** Clave del icono (ver `app/layouts/default.vue`). */
  icon: 'intake' | 'reception' | 'printer' | 'sample' | 'inbox' | 'results' | 'catalog' | 'trace' | 'settings'
}

export const SCREENS: ScreenItem[] = [
  { section: 'Atención', label: 'Pre-recepción', to: '/pre-recepcion', tag: TAGS.preReception.view, icon: 'intake' },
  { section: 'Atención', label: 'Recepción', to: '/recepcion', tag: TAGS.reception.view, icon: 'reception' },
  { section: 'Toma de muestras', label: 'Impresión de etiquetas', to: '/impresion-etiquetas', tag: TAGS.labelPrinting.view, icon: 'printer' },
  { section: 'Toma de muestras', label: 'Toma de muestras', to: '/toma-muestras', tag: TAGS.sampling.view, icon: 'sample' },
  { section: 'Laboratorio', label: 'Recepción laboratorio', to: '/recepcion-laboratorio', tag: TAGS.labReception.view, icon: 'inbox' },
  { section: 'Laboratorio', label: 'Resultados', to: '/resultados', tag: TAGS.results.view, icon: 'results' },
  { section: 'Laboratorio', label: 'Trazabilidad', to: '/trazabilidad', tag: TAGS.results.trace, icon: 'trace' },
  { section: 'Administración', label: 'Catálogos de la cola', to: '/catalogos-cola', tag: TAGS.queueAdmin.view, icon: 'catalog' },
  { section: 'Administración', label: 'Ajustes del sistema', to: '/ajustes', tag: TAGS.settings.view, icon: 'settings' }
]

/** Pantallas que el usuario puede abrir. */
export function visibleScreens(can: CanFn): ScreenItem[] {
  return SCREENS.filter((screen) => can(screen.tag))
}

/** Ruta de la primera pantalla visible, o `null` si no tiene acceso a ninguna. */
export function firstVisibleRoute(can: CanFn): string | null {
  return visibleScreens(can)[0]?.to ?? null
}
