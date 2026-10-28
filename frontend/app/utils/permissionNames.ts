import { TAG_NAMES } from './tags'

/**
 * Nombres legibles de los permisos (tags) de Incubus, para mensajes al
 * usuario ("No tienes permiso para: …"). Se registran en leo-client (plugin
 * permissionNames) para sus mensajes 403. Derivados del contrato generado del
 * backend (`app/generated/permissions.json`); no se editan a mano.
 */
export const PERMISSION_NAMES: Record<string, string> = TAG_NAMES
