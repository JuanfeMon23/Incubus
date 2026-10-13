import { wsUrlFromApiBase } from '../utils/format'

// Estado compartido de la conexion y contador de eventos: las vistas observan
// `version` y vuelven a listar (el servidor es la fuente del orden).
const live = ref(false)
const version = ref(0)
let socket: WebSocket | null = null
let retry: ReturnType<typeof setTimeout> | null = null
let attempts = 0

function connect(apiBase: string) {
  retry = null
  socket = new WebSocket(wsUrlFromApiBase(apiBase))
  socket.onopen = () => {
    live.value = true
    attempts = 0
    version.value++ // re-sincroniza al (re)conectar
  }
  socket.onmessage = () => {
    version.value++
  }
  socket.onclose = () => {
    live.value = false
    socket = null
    attempts++
    retry = setTimeout(() => connect(apiBase), Math.min(1000 * 2 ** attempts, 15000))
  }
  socket.onerror = () => socket?.close()
}

export function useQueueSocket() {
  if (import.meta.client && !socket && !retry) {
    const base = useRuntimeConfig().public.apiBase
    if (base) connect(base)
  }
  return { live, version }
}
