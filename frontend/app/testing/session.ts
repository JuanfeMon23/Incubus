import { useState } from '#imports'
import { ALL_TAGS } from '../utils/tags'

/**
 * Deja una sesión de Leo autenticada con los tags dados (solo tests de
 * componentes/páginas con `LeoCan`/`useCan`/middleware). Nuxt no auto-importa `app/testing/`.
 * `signInWith(ALL)` da todos los permisos de Incubus.
 */
export function signInWith(permissions: string[]) {
  useState('leo-session').value = {
    status: 'authenticated',
    me: {
      user: { id: 'u1', username: 'ana', email: 'a@x.co', first_name: 'Ana', last_name: 'Pérez' },
      session: { id: 's', expires_at: '', last_activity_at: '', idle_timeout_seconds: 0 },
      permissions,
      applications: []
    }
  }
}

/** Los 24 permisos de Incubus. */
export const ALL = [...ALL_TAGS]
/** Todos menos los indicados (para comprobar que sin ese tag la acción no se renderiza). */
export const allExcept = (...tags: string[]) => ALL.filter((tag) => !tags.includes(tag))
