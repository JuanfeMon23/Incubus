import { describe, expect, it, vi } from 'vitest'
// La misma firma DPoP que usa leo-client para las peticiones (llave de la sesión).
import { base64UrlDecode, createDpopSigner, memoryDpopKeyStore } from '../../node_modules/leo-client/app/lib/dpop'
import { createSocketAuth, socketHtu } from './socketAuth'

const decode = (jws: string) => {
  const [header, payload] = jws.split('.')
  const json = (part: string) => JSON.parse(new TextDecoder().decode(base64UrlDecode(part)))
  return { header: json(header!), payload: json(payload!) }
}

describe('socketHtu', () => {
  it('es la URL pública + /socket.io/ (barra final, sin query)', () => {
    expect(socketHtu('http://localhost:8001')).toBe('http://localhost:8001/socket.io/')
    expect(socketHtu('http://localhost:8001/')).toBe('http://localhost:8001/socket.io/')
  })
})

describe('auth del socket', () => {
  it('firma GET sobre PUBLIC_URL/socket.io/ y devuelve { dpop }', async () => {
    const sign = vi.fn().mockResolvedValue('jws')
    expect(await createSocketAuth(sign, 'http://localhost:8001')()).toEqual({ dpop: 'jws' })
    expect(sign).toHaveBeenCalledWith('GET', 'http://localhost:8001/socket.io/')
  })

  it('con la llave real: htm/htu correctos, iat actual y un jti distinto en cada llamada', async () => {
    const signer = await createDpopSigner(memoryDpopKeyStore())
    const auth = createSocketAuth((htm, htu) => signer.proof(htm, htu), 'http://localhost:8001')
    const before = Math.floor(Date.now() / 1000)
    const [a, b] = await Promise.all([auth(), auth()])
    const first = decode(a.dpop)
    const second = decode(b.dpop)
    expect(first.header).toMatchObject({ typ: 'dpop+jwt', alg: 'ES256' })
    expect(first.payload).toMatchObject({ htm: 'GET', htu: 'http://localhost:8001/socket.io/' })
    expect(Math.abs(first.payload.iat - before)).toBeLessThan(5)
    expect(first.payload.jti).toBeTruthy()
    expect(first.payload.jti).not.toBe(second.payload.jti)
    expect(a.dpop).not.toBe(b.dpop)
  })
})
