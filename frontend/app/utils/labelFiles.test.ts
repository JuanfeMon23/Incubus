import { describe, expect, it, vi } from 'vitest'
import { createLabelFiles, labelsFilename, labelsPath } from './labelFiles'
import { safeDownloadName } from './downloadBlob'

const blob = new Blob(['x'])

function setup(fetchBlob = vi.fn().mockResolvedValue(blob)) {
  const showPdf = vi.fn()
  const saveFile = vi.fn()
  return { fetchBlob, showPdf, saveFile, files: createLabelFiles({ fetchBlob, showPdf, saveFile }) }
}

describe('etiquetas por petición firmada', () => {
  it('construye las rutas de PDF y ZPL', () => {
    expect(labelsPath('e1', 'pdf')).toBe('/orders/by-entry/e1/labels.pdf')
    expect(labelsPath('e1', 'zpl')).toBe('/orders/by-entry/e1/labels.zpl')
  })

  it('nombra el archivo con el número de orden', () => {
    expect(labelsFilename('2610-0001', 'zpl')).toBe('etiquetas-2610-0001.zpl')
    expect(labelsFilename(null, 'pdf')).toBe('etiquetas-orden.pdf')
  })

  it('el PDF se pide con la petición firmada y se muestra desde el blob', async () => {
    const { files, fetchBlob, showPdf, saveFile } = setup()
    await files.openPdf('e1', '2610-0001')
    expect(fetchBlob).toHaveBeenCalledWith('/orders/by-entry/e1/labels.pdf')
    expect(showPdf).toHaveBeenCalledWith(blob, 'etiquetas-2610-0001.pdf')
    expect(saveFile).not.toHaveBeenCalled()
  })

  it('el ZPL se pide firmado y se guarda como archivo', async () => {
    const { files, fetchBlob, showPdf, saveFile } = setup()
    await files.downloadZpl('e1', '2610-0001')
    expect(fetchBlob).toHaveBeenCalledWith('/orders/by-entry/e1/labels.zpl')
    expect(saveFile).toHaveBeenCalledWith(blob, 'etiquetas-2610-0001.zpl')
    expect(showPdf).not.toHaveBeenCalled()
  })

  it('si la petición falla no se muestra nada y el error sube a quien llama', async () => {
    const { files, showPdf, saveFile } = setup(vi.fn().mockRejectedValue(new Error('403')))
    await expect(files.openPdf('e1')).rejects.toThrow('403')
    await expect(files.downloadZpl('e1')).rejects.toThrow('403')
    expect(showPdf).not.toHaveBeenCalled()
    expect(saveFile).not.toHaveBeenCalled()
  })
})

describe('safeDownloadName', () => {
  it('quita separadores de ruta y caracteres de control', () => {
    expect(safeDownloadName('../a/b\\c\u0000.zpl')).toBe('a-b-c.zpl')
    expect(safeDownloadName('   ')).toBe('descarga')
  })
})
