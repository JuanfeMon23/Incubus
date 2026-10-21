import { describe, expect, it } from 'vitest'

describe('configuración de leo-client en Incubus', () => {
  it('usa el transporte bff contra el backend de la app, con /auth y el callback propio', () => {
    const leo = useRuntimeConfig().public.leo
    expect(leo.transport).toBe('bff')
    expect(leo.authPath).toBe('/auth')
    expect(leo.callbackPath).toBe('/leo/callback')
    expect(leo.appSlug).toBe('incubus')
    expect(leo.appName).toBe('Incubus')
  })

  it('la API de Incubus cuelga de la base de Leo (una sola URL de backend)', () => {
    const { apiBase, leo } = useRuntimeConfig().public
    expect(apiBase.startsWith(leo.apiBase)).toBe(true)
  })

  it('la página de retorno de login está registrada en /leo/callback', () => {
    expect(useRouter().resolve('/leo/callback').matched.length).toBeGreaterThan(0)
  })

  it('toda pantalla exige su tag view como metadato de ruta', () => {
    const tagOf = (path: string) => (useRouter().resolve(path).meta as { leo?: { tag?: string } }).leo?.tag
    expect(tagOf('/pre-recepcion')).toBe('incubus.pre-reception.view')
    expect(tagOf('/recepcion')).toBe('incubus.reception.view')
    expect(tagOf('/impresion-etiquetas')).toBe('incubus.label-printing.view')
    expect(tagOf('/toma-muestras')).toBe('incubus.sampling.view')
    expect(tagOf('/recepcion-laboratorio')).toBe('incubus.lab-reception.view')
    expect(tagOf('/resultados')).toBe('incubus.results.view')
  })
})
