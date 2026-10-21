import { describe, expect, it } from 'vitest'
import { toLeoPath } from './leoPaths'

describe('toLeoPath', () => {
  it('antepone el prefijo de la API (apiBase menos la base de Leo) a la ruta', () => {
    expect(toLeoPath('http://localhost:8001/api/v1', 'http://localhost:8001', '/lab-areas')).toBe('/api/v1/lab-areas')
  })

  it('tolera barras finales y rutas sin barra inicial', () => {
    expect(toLeoPath('http://localhost:8001/api/v1/', 'http://localhost:8001/', 'staff')).toBe('/api/v1/staff')
  })

  it('sin prefijo (misma base) deja la ruta tal cual', () => {
    expect(toLeoPath('http://localhost:8001', 'http://localhost:8001', '/staff')).toBe('/staff')
  })

  it('falla con un mensaje claro si la API no cuelga de la base de Leo', () => {
    expect(() => toLeoPath('http://api.test/api/v1', 'http://localhost:8001', '/staff')).toThrow(/NUXT_PUBLIC_LEO_API_BASE/)
  })
})
