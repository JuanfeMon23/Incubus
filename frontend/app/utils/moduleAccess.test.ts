import { describe, expect, it } from 'vitest'
import { firstVisibleRoute, SCREENS, stagesWithView, STAGE_VIEW_TAG, visibleScreens } from './moduleAccess'
import { TAGS } from './tags'

const canOnly = (...tags: string[]) => (tag: string) => tags.includes(tag)

describe('menú por permiso', () => {
  it('cada pantalla exige el view de su etapa', () => {
    expect(Object.fromEntries(SCREENS.map((s) => [s.to, s.tag]))).toEqual({
      '/pre-recepcion': TAGS.preReception.view,
      '/recepcion': TAGS.reception.view,
      '/impresion-etiquetas': TAGS.labelPrinting.view,
      '/toma-muestras': TAGS.sampling.view,
      '/recepcion-laboratorio': TAGS.labReception.view,
      '/resultados': TAGS.results.view,
      '/trazabilidad': TAGS.results.trace,
      '/catalogos-cola': TAGS.queueAdmin.view
    })
  })

  it('sin permisos no hay pantallas ni ruta de inicio', () => {
    expect(visibleScreens(canOnly())).toEqual([])
    expect(firstVisibleRoute(canOnly())).toBeNull()
  })

  it('solo se ven las pantallas con view (los permisos de acción no abren pantallas)', () => {
    const can = canOnly(TAGS.reception.view, TAGS.sampling.view, TAGS.results.enter)
    expect(visibleScreens(can).map((s) => s.label)).toEqual(['Recepción', 'Toma de muestras'])
  })

  it('el inicio lleva a la primera pantalla visible', () => {
    expect(firstVisibleRoute(canOnly(TAGS.results.view, TAGS.labelPrinting.view))).toBe('/impresion-etiquetas')
  })

  it.each([
    [[TAGS.sampling.view], '/toma-muestras'],
    [[TAGS.reception.view, TAGS.results.view], '/recepcion'],
    [[TAGS.results.view, TAGS.labReception.view], '/recepcion-laboratorio'],
    [[TAGS.preReception.view, TAGS.results.view], '/pre-recepcion'],
    [[TAGS.results.enter, TAGS.sampling.claim], null]
  ])('primer módulo con view para %j es %s', (tags, route) => {
    expect(firstVisibleRoute(canOnly(...tags))).toBe(route)
  })
})

describe('etapas visibles', () => {
  it('espeja el STAGE_VIEW del backend', () => {
    expect(STAGE_VIEW_TAG.en_atencion_toma_muestras).toBe(TAGS.sampling.view)
    expect(STAGE_VIEW_TAG.toma_finalizada).toBe(TAGS.labReception.view)
    expect(STAGE_VIEW_TAG.en_laboratorio).toBe(TAGS.results.view)
  })

  it('filtra las etapas cuyo view no se tiene (el servidor rechaza el pedido entero si falta una)', () => {
    const can = canOnly(TAGS.reception.view)
    expect(stagesWithView(['pre_recepcion', 'en_atencion_recepcion'], can)).toEqual(['en_atencion_recepcion'])
    expect(stagesWithView(['pre_recepcion'], can)).toEqual([])
  })
})
