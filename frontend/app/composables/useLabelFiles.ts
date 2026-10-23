import { downloadBlob, openBlobInTab } from '#andromeda/utils/downloadBlob'
import { createLabelFiles } from '../utils/labelFiles'

/**
 * PDF y ZPL de etiquetas: el backend exige DPoP, así que no se abren con
 * `<a href>`/`window.open` directo; se piden con el solicitante firmado como
 * `Blob` y se muestran/guardan desde un object URL. Los errores son
 * `LeoApiError` (usar `leoErrorMessage`).
 */
export function useLabelFiles() {
  const api = useLeoAppApi()
  return createLabelFiles({
    fetchBlob: (path) => api.get<Blob>(path, { responseType: 'blob' }),
    showPdf: openBlobInTab,
    saveFile: downloadBlob
  })
}
