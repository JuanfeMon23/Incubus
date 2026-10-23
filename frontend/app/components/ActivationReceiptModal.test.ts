import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { findButton, flushAll } from '~/testing/dom'
import ActivationReceiptModal from './ActivationReceiptModal.vue'

enableAutoUnmount(afterEach)
beforeEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
})

const props = { orderNumber: '2610-0001', activationCode: 'ABCDE-FGHJK' }

describe('ActivationReceiptModal', () => {
  it('muestra orden, código, vigencia y aviso de única vez', async () => {
    await mountSuspended(ActivationReceiptModal, { props })
    await flushAll()
    const text = document.body.textContent ?? ''
    expect(text).toContain('2610-0001')
    expect(text).toContain('ABCDE-FGHJK')
    expect(text).toContain('Código de activación de Acuarius (portal de pacientes para ver sus resultados)')
    expect(text).toContain('30 días')
    expect(text).toContain('Este código solo se muestra ahora; no se puede recuperar.')
    expect(document.querySelector('[data-testid="receipt-code"]')!.className).toContain('font-mono')
  })

  it('Copiar escribe el código en el portapapeles; Imprimir llama a window.print', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const print = vi.fn()
    Object.defineProperty(window, 'print', { value: print, configurable: true })
    await mountSuspended(ActivationReceiptModal, { props })
    await flushAll()
    findButton(document.body, 'Copiar')!.click()
    await flushAll()
    expect(writeText).toHaveBeenCalledWith('ABCDE-FGHJK')
    findButton(document.body, 'Imprimir')!.click()
    expect(print).toHaveBeenCalled()
  })

  it('no persiste el código en localStorage ni sessionStorage', async () => {
    await mountSuspended(ActivationReceiptModal, { props })
    await flushAll()
    const dump = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage })
    expect(dump).not.toContain('ABCDE-FGHJK')
  })
})
