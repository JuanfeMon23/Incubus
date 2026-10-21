import { createDpopSigner, indexedDbDpopKeyStore, memoryDpopKeyStore } from '#leo-client/lib/dpop'
import { createSocketAuth } from '../utils/socketAuth'

/**
 * Autentica el socket con Leo: en cada (re)conexión firma una prueba DPoP nueva
 * (`htm=GET`, `htu=<PUBLIC_URL>/socket.io/`) con la MISMA llave de la sesión.
 *
 * leo-client no expone una forma pública de firmar una prueba arbitraria
 * (`$leo.transport` solo ofrece `request` y `jkt`), así que se abre el mismo
 * almacén de llaves (IndexedDB `leo-client`) con su módulo `lib/dpop`. El
 * firmante se crea en cada llamada (no se cachea) para seguir la llave actual
 * si la sesión la renueva tras cerrar sesión. Requisito para leo-client:
 * exponer `$leo.transport.proof(htm, htu)`.
 */
export default defineNuxtPlugin(() => {
  const { publicUrl } = useRuntimeConfig().public.leo
  const sign = async (htm: string, htu: string) => {
    const store = typeof indexedDB === 'undefined' ? memoryDpopKeyStore() : indexedDbDpopKeyStore()
    return (await createDpopSigner(store)).proof(htm, htu)
  }
  setQueueSocketAuth(createSocketAuth(sign, publicUrl))
})
