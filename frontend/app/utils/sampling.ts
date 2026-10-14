import type { OrderSample } from '../types'

export function pendingSamples(samples: OrderSample[]): OrderSample[] {
  return samples.filter((s) => !s.collected_at)
}

export function allCollected(samples: OrderSample[]): boolean {
  return samples.length > 0 && pendingSamples(samples).length === 0
}

/** "5 mL" / "" cuando el examen no define volumen. */
export function formatVolume(ml: number | null): string {
  if (ml === null || ml === undefined) return ''
  return `${Number.isInteger(ml) ? ml : ml.toFixed(1)} mL`
}
