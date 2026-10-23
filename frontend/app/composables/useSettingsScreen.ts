import type { SettingHistoryPage, SettingItem, SettingsListResponse, SettingUpdateBody } from '#andromeda/types/settings'
import { useSettingsAdmin } from '#andromeda/composables/useSettingsAdmin'
import { TAGS } from '../utils/tags'

/** Llamadas a `/settings` de Incubus con el cliente de Leo (lanzan `LeoApiError`). */
export function useSettingsApi() {
  const api = useLeoAppApi()
  const path = (key: string) => `/settings/${encodeURIComponent(key)}`
  return {
    list: () => api.get<SettingsListResponse>('/settings'),
    history: (key: string, page: number) => api.get<SettingHistoryPage>(`${path(key)}/history`, { query: { page } }),
    update: (key: string, body: SettingUpdateBody) => api.put<SettingItem>(path(key), body)
  }
}

/**
 * Estado de la pantalla «Ajustes del sistema»: conecta `useSettingsAdmin` de Andromeda con la API,
 * los permisos de la sesión, los avisos y los mensajes legibles. Editar exige `settings.edit`;
 * los ajustes de seguridad, además `settings.edit-security`.
 */
export function useSettingsScreen() {
  const api = useSettingsApi()
  const toast = useToast()
  return useSettingsAdmin({
    ...api,
    canEdit: useCan(TAGS.settings.edit),
    canEditSecurity: useCan(TAGS.settings.editSecurity),
    mapError: (err) => leoErrorMessage(err),
    notify: (kind, message) => toast[kind](message)
  })
}
