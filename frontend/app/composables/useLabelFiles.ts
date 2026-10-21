import { downloadBlob, openBlobInTab } from '../utils/downloadBlob'
import { createLabelFiles } from '../utils/labelFiles'

/**
 * PDF y ZPL de etiquetas: el backend exige DPoP, así que no se abren con
 * `<a href>`/`window.open` directo; se piden con el solicitante firmado como
 * `Blob` y se muestran/guardan desde un object URL. Los errores son
 * `LeoApiError` (usar `apiErrorMessage`).
 */
export function useLabelFiles() {
  const api = useApi()
  return createLabelFiles({
    fetchBlob: (path) => api<Blob>(path, { responseType: 'blob' }),
    showPdf: openBlobInTab,
    saveFile: downloadBlob
  })
}
