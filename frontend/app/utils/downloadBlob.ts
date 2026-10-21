/**
 * Descarga/visualización de archivos que la API solo entrega con petición
 * firmada (DPoP): se piden como `Blob` y se muestran desde un object URL.
 * Mismo patrón que `frontend/app/utils/downloadBlob.ts` de Leo.
 */

/** Nombre de archivo seguro: sin separadores de ruta ni caracteres de control. */
export function safeDownloadName(name: string): string {
  const cleaned = name
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .replace(/[\\/]+/g, '-')
    .replace(/^[-.\s]+/, '')
    .trim()
  return cleaned || 'descarga'
}

/** Tiempo que vive el object URL de una pestaña abierta (la pestaña lo necesita para cargar). */
export const OBJECT_URL_TTL_MS = 60_000

/** Guarda un `Blob` como archivo en el navegador (enlace temporal con `download`). */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = safeDownloadName(filename)
  link.rel = 'noopener'
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * Muestra un `Blob` (p. ej. un PDF) en otra pestaña desde un object URL, que se
 * revoca después. Si el navegador bloquea la pestaña, lo descarga como archivo.
 */
export function openBlobInTab(blob: Blob, fallbackFilename: string): void {
  const url = URL.createObjectURL(blob)
  const tab = window.open(url, '_blank')
  if (!tab) {
    URL.revokeObjectURL(url)
    downloadBlob(blob, fallbackFilename)
    return
  }
  setTimeout(() => URL.revokeObjectURL(url), OBJECT_URL_TTL_MS)
}
