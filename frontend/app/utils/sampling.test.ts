import { describe, expect, it } from 'vitest'
import type { OrderSample } from '../types'
import { allCollected, formatVolume, pendingSamples } from './sampling'

const tube = (collected: boolean): OrderSample => ({
  id: String(Math.random()),
  sample_type_code: 'RED',
  name: 'Tapa roja',
  cap_color_hex: '#DC2626',
  draw_order: 1,
  collection_instructions: null,
  required_volume_ml: 3,
  test_codes: ['COL'],
  collected_at: collected ? '2026-10-14T10:00:00Z' : null,
  collected_by: collected ? 'luis' : null
})

describe('sampling', () => {
  it('pendingSamples lista solo los no tomados', () => {
    expect(pendingSamples([tube(true), tube(false)])).toHaveLength(1)
  })

  it('allCollected exige al menos un tubo y ninguno pendiente', () => {
    expect(allCollected([])).toBe(false)
    expect(allCollected([tube(true), tube(false)])).toBe(false)
    expect(allCollected([tube(true), tube(true)])).toBe(true)
  })

  it('formatVolume', () => {
    expect(formatVolume(5)).toBe('5 mL')
    expect(formatVolume(2.5)).toBe('2.5 mL')
    expect(formatVolume(null)).toBe('')
  })
})
