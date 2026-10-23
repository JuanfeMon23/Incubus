import { ALL_TAGS } from '../utils/tags'

// `signInWith` (sesión de Leo autenticada con los tags dados) viene de leo-client:
// `import { signInWith } from '#leo-client/testing/session'`.

/** Los 30 permisos de Incubus. */
export const ALL = [...ALL_TAGS]
/** Todos menos los indicados (para comprobar que sin ese tag la acción no se renderiza). */
export const allExcept = (...tags: string[]) => ALL.filter((tag) => !tags.includes(tag))
