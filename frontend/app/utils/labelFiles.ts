export type LabelFormat = 'pdf' | 'zpl'

/** Ruta del archivo de etiquetas de una entrada (exige `label-printing.print` y prueba DPoP). */
export function labelsPath(entryId: string, format: LabelFormat): string {
  return `/orders/by-entry/${entryId}/labels.${format}`
}

/** Nombre del archivo al descargar (el número de orden si se conoce). */
export function labelsFilename(orderNumber: string | null | undefined, format: LabelFormat): string {
  return `etiquetas-${orderNumber || 'orden'}.${format}`
}

export interface LabelFilesDeps {
  /** Petición firmada que devuelve el archivo como `Blob`. */
  fetchBlob: (path: string) => Promise<Blob>
  /** Muestra el PDF (object URL en otra pestaña). */
  showPdf: (blob: Blob, filename: string) => void
  /** Guarda un archivo en el equipo. */
  saveFile: (blob: Blob, filename: string) => void
}

/**
 * Las etiquetas ya no se abren con `<a href>`/`window.open` directo a la API
 * (el backend exige DPoP): se descargan con la petición firmada y se muestran
 * desde un object URL. Los errores suben a quien llama (que los hace legibles).
 */
export function createLabelFiles(deps: LabelFilesDeps) {
  return {
    async openPdf(entryId: string, orderNumber?: string | null): Promise<void> {
      deps.showPdf(await deps.fetchBlob(labelsPath(entryId, 'pdf')), labelsFilename(orderNumber, 'pdf'))
    },
    async downloadZpl(entryId: string, orderNumber?: string | null): Promise<void> {
      deps.saveFile(await deps.fetchBlob(labelsPath(entryId, 'zpl')), labelsFilename(orderNumber, 'zpl'))
    }
  }
}
