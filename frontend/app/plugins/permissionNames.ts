import { PERMISSION_NAMES } from '../utils/permissionNames'

// Nombres legibles de los permisos de Incubus para los 403 y los avisos de la UI.
export default defineNuxtPlugin(() => {
  registerPermissionNames(PERMISSION_NAMES)
})
