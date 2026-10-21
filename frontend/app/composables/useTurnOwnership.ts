import type { QueueEntry } from '../types'
import { canActOnTurn, superviseTagFor, turnOwnerHint } from '../utils/turnOwnership'

/**
 * Propiedad del turno en atención (recepción o toma): ¿puede el usuario actual
 * actuar sobre él? Solo el dueño o un supervisor de la etapa. `hint(acción)` da
 * el aviso legible para `title`/`UiAlert`. Compartido por recepcion.vue y toma-muestras.vue.
 */
export function useTurnOwnership(entry: Ref<QueueEntry | null>) {
  const user = useLeoUser()
  // `useCan` acepta un getter: el tag cambia con la etapa del turno (sin tag, `can([])` no concede nada).
  const canSupervise = useCan(() => superviseTagFor(entry.value?.status) ?? '__none__')
  const ownsTurn = computed(() => !entry.value || canActOnTurn(entry.value, user.value, canSupervise.value))
  const hint = (action: string) => (entry.value ? turnOwnerHint(entry.value, action) : '')
  return { ownsTurn, hint }
}
