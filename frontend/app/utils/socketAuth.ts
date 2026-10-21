/**
 * Autenticación del socket (contrato del backend, `app/core/realtime.py`): un
 * WebSocket del navegador no puede enviar el header `DPoP`, así que la prueba
 * va en `auth.dpop`: ES256 con la llave de la sesión, `htm="GET"` y
 * `htu = <PUBLIC_URL del backend>/socket.io/` (con la barra final, sin query).
 * Cada intento/reconexión necesita una prueba nueva (anti-replay por `jti`).
 */
export const SOCKET_HTM = 'GET'

export function socketHtu(publicUrl: string): string {
  return `${publicUrl.replace(/\/+$/, '')}/socket.io/`
}

/** Firma una prueba DPoP (`htm`, `htu`) con la llave de la sesión. */
export type SignProof = (htm: string, htu: string) => Promise<string>

/** `auth` del socket: una función que genera la prueba en cada (re)conexión. */
export function createSocketAuth(sign: SignProof, publicUrl: string): () => Promise<{ dpop: string }> {
  return async () => ({ dpop: await sign(SOCKET_HTM, socketHtu(publicUrl)) })
}
