import type { QueueEntry, QueueStatus } from '../types'

/** Lista de la cola filtrada por estados; se refresca con cada evento en vivo. */
export function useQueueList(statuses: QueueStatus[]) {
  const api = useApi()
  const { version } = useQueueSocket()
  const entries = ref<QueueEntry[]>([])
  const error = ref('')

  async function refresh() {
    try {
      const qs = statuses.map((s) => `status=${s}`).join('&')
      entries.value = await api<QueueEntry[]>(`/queue?${qs}`)
      error.value = ''
    } catch (e) {
      error.value = apiErrorMessage(e)
    }
  }

  onMounted(refresh)
  watch(version, refresh)
  return { entries, error, refresh }
}
