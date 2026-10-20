import { ref } from 'vue'
import { decideEvent, patchEntry, snapshotDiffers, sortQueue, stageRoom } from './queueLive'
import type { LiveEntry, LiveEvent, LiveEventName } from './queueLive'
import type { RealtimeSubscriber } from './queueRealtime'
import type { QueueEntry, QueueStatus } from '../types'

export interface QueueListDeps {
  subscribe: (sub: RealtimeSubscriber) => () => void
  fetchList: (statuses: QueueStatus[]) => Promise<QueueEntry[]>
  fetchOne: (id: string) => Promise<QueueEntry>
  toMessage: (e: unknown) => string
  /** Gancho para pantallas que reaccionan a eventos (p. ej. `sample:updated`). */
  onEvent?: (name: LiveEventName, ev: LiveEvent) => void
}

/**
 * Lista de la cola por etapas, mantenida con diffs de Socket.IO. REST completo
 * solo en la carga inicial, en `refresh()` (tras acciones propias) y cuando el
 * `sync` detecta divergencia; las entradas nuevas se piden una a una.
 */
export function createQueueList(statuses: QueueStatus[], deps: QueueListDeps) {
  const entries = ref<QueueEntry[]>([])
  const error = ref('')
  // true solo mientras no hay datos aún (primera carga): las recargas no parpadean.
  const loading = ref(true)
  const seen = new Map<string, number>() // última versión vista por entrada
  let listing = false
  let buffer: Array<[LiveEventName, LiveEvent]> = []
  let pendingSnapshot: LiveEntry[] | null = null
  let unsubscribe: (() => void) | null = null

  const inStage = (s: QueueStatus) => statuses.includes(s)
  const remember = (id: string, version: number) => seen.set(id, Math.max(seen.get(id) ?? -1, version))

  function upsert(entry: QueueEntry) {
    entries.value = sortQueue([...entries.value.filter((e) => e.id !== entry.id), entry])
  }

  function applyFetched(entry: QueueEntry) {
    if (entry.version < (seen.get(entry.id) ?? -1)) return // respuesta vieja
    remember(entry.id, entry.version)
    if (inStage(entry.status)) upsert(entry)
    else entries.value = entries.value.filter((e) => e.id !== entry.id)
  }

  async function fetchEntry(id: string) {
    try {
      applyFetched(await deps.fetchOne(id))
    } catch (e) {
      error.value = deps.toMessage(e)
    }
  }

  async function refresh() {
    listing = true
    try {
      const list = await deps.fetchList(statuses)
      for (const e of list) remember(e.id, e.version)
      entries.value = sortQueue(list)
      error.value = ''
    } catch (e) {
      error.value = deps.toMessage(e)
    } finally {
      listing = false
      loading.value = false
    }
    // Eventos que llegaron mientras se listaba: la guarda por versión descarta los viejos.
    const queued = buffer
    buffer = []
    for (const [name, ev] of queued) handle(name, ev)
    if (pendingSnapshot) {
      const snap = pendingSnapshot
      pendingSnapshot = null
      reconcile(snap)
    }
  }

  function handle(name: LiveEventName, ev: LiveEvent) {
    if (listing) {
      buffer.push([name, ev])
      return
    }
    deps.onEvent?.(name, ev)
    const known = entries.value.find((e) => e.id === ev.id)
    const decision = decideEvent(name, ev, known, seen.get(ev.id), statuses)
    if (decision === 'ignore') {
      remember(ev.id, ev.version)
    } else if (decision === 'remove') {
      remember(ev.id, ev.version)
      entries.value = entries.value.filter((e) => e.id !== ev.id)
    } else if (decision === 'patch') {
      remember(ev.id, ev.version)
      upsert(patchEntry(known!, ev))
    } else {
      void fetchEntry(ev.id)
    }
  }

  function reconcile(snapshot: LiveEntry[]) {
    if (listing) {
      pendingSnapshot = snapshot
      return
    }
    const mine = snapshot.filter((s) => inStage(s.status))
    if (snapshotDiffers(entries.value, mine)) void refresh()
  }

  function start() {
    unsubscribe = deps.subscribe({
      rooms: statuses.map(stageRoom),
      onEvent: handle,
      onSync: reconcile
    })
    return refresh()
  }

  function stop() {
    unsubscribe?.()
    unsubscribe = null
  }

  return { entries, error, loading, refresh, start, stop }
}

/** Refresca (con debounce) un endpoint propio ante eventos de las etapas dadas. */
export function createQueueRefresh(
  statuses: QueueStatus[],
  load: () => unknown,
  deps: Pick<QueueListDeps, 'subscribe'> & { debounceMs?: number; enabled?: () => boolean }
) {
  let timer: ReturnType<typeof setTimeout> | undefined
  let unsubscribe: (() => void) | null = null
  const trigger = () => {
    clearTimeout(timer)
    timer = setTimeout(() => {
      if (!deps.enabled || deps.enabled()) void load()
    }, deps.debounceMs ?? 300)
  }
  return {
    start() {
      unsubscribe = deps.subscribe({ rooms: statuses.map(stageRoom), onEvent: trigger, onSync: trigger })
    },
    stop() {
      clearTimeout(timer)
      unsubscribe?.()
      unsubscribe = null
    }
  }
}
