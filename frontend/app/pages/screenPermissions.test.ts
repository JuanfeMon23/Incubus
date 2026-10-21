import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { buttonTexts, findButton, flushAll } from '~/testing/dom'
import { entry, labOrder, order, sample } from '~/testing/fixtures'
import { ALL, allExcept, signInWith } from '~/testing/session'
import { TAGS } from '~/utils/tags'
import ExamValidationForm from '../components/ExamValidationForm.vue'
import ImpresionPage from './impresion-etiquetas.vue'
import LabReceptionPage from './recepcion-laboratorio.vue'
import PreReceptionPage from './pre-recepcion.vue'
import ReceptionPage from './recepcion.vue'
import ResultsPage from './resultados.vue'
import SamplingPage from './toma-muestras.vue'

const fake = await vi.hoisted(async () => (await import('~/testing/fakeApi')).createFakeApi())
mockNuxtImport('useApi', () => () => fake.api)
// Sin conexión real: el socket se prueba aparte (queueRealtime.test.ts).
mockNuxtImport('useQueueSocket', () => () => ({
  connected: { value: true },
  reconnecting: { value: false },
  error: { value: '' },
  subscribe: () => () => {},
  open: () => {},
  close: () => {}
}))
const files = vi.hoisted(() => ({ showPdf: vi.fn(), saveFile: vi.fn() }))
vi.mock('../utils/downloadBlob', () => ({ openBlobInTab: files.showPdf, downloadBlob: files.saveFile }))

enableAutoUnmount(afterEach)

const STAFF = { id: 'st1', name: 'Marta Ruiz', job_title: 'Toma de muestras' }

beforeEach(() => {
  fake.reset()
  files.showPdf.mockReset()
  files.saveFile.mockReset()
  document.body.innerHTML = ''
  fake.routes['GET /catalog/staff'] = [STAFF]
})

/** Parte del wrapper de @vue/test-utils que usan las pruebas (evita ligar el tipo a cada componente). */
interface Mounted {
  element: Element
  text: () => string
  find: (selector: string) => { element: any, trigger: (event: string) => Promise<void> }
}

async function mountPage(page: object, tags: string[]): Promise<Mounted> {
  signInWith(tags)
  const wrapper = await mountSuspended(page)
  await flushAll()
  return wrapper as unknown as Mounted
}

/** Abre la tarjeta seleccionable de la entrada (como un clic del usuario). */
async function selectCard(wrapper: Mounted) {
  await wrapper.find('article[role="button"]').trigger('click')
  await flushAll()
}

/** Botón por texto: `null` si la acción no se renderiza. */
const btn = (wrapper: Mounted, text: string) => findButton(wrapper.element, text)

describe('pre-recepción', () => {
  beforeEach(() => {
    fake.routes['GET /queue'] = [entry('pre_recepcion')]
  })

  it('exige pre-reception.view como metadato de ruta', () => {
    expect((useRouter().resolve('/pre-recepcion').meta as { leo?: { tag?: string } }).leo?.tag).toBe(
      TAGS.preReception.view
    )
  })

  it('sin enqueue no hay formulario de ingreso; con enqueue sí', async () => {
    expect((await mountPage(PreReceptionPage, [TAGS.preReception.view])).text()).not.toContain('Ingresar a la cola')
    expect((await mountPage(PreReceptionPage, [TAGS.preReception.view, TAGS.preReception.enqueue])).text()).toContain(
      'Ingresar a la cola'
    )
  })

  it('"Retirar" solo con remove', async () => {
    expect(btn(await mountPage(PreReceptionPage, allExcept(TAGS.preReception.remove)), 'Retirar')).toBeNull()
    expect(btn(await mountPage(PreReceptionPage, [TAGS.preReception.view, TAGS.preReception.remove]), 'Retirar')).not.toBeNull()
  })
})

describe('recepción', () => {
  beforeEach(() => {
    fake.routes['GET /queue'] = [entry('pre_recepcion', 'w1'), entry('en_atencion_recepcion', 'a1')]
  })

  it('"Llamar al siguiente" solo con call-next, y la llamada no envía actor', async () => {
    expect(btn(await mountPage(ReceptionPage, allExcept(TAGS.reception.callNext)), 'Llamar al siguiente')).toBeNull()
    const wrapper = await mountPage(ReceptionPage, ALL)
    fake.routes['POST /queue/call-next'] = entry('en_atencion_recepcion', 'w1')
    btn(wrapper, 'Llamar al siguiente')!.click()
    await flushAll()
    expect(fake.requests).toHaveBeenCalledWith('POST', '/queue/call-next', { method: 'POST' })
  })

  it('sin pre-reception.view no se ve la lista de espera pero sí se puede llamar al siguiente', async () => {
    const wrapper = await mountPage(ReceptionPage, allExcept(TAGS.preReception.view))
    expect(wrapper.text()).not.toContain('en espera')
    expect(btn(wrapper, 'Llamar al siguiente')?.disabled).toBe(false)
    // Solo pide las etapas visibles: el servidor rechazaría el pedido entero por la que falta.
    expect(fake.requests).toHaveBeenCalledWith('GET', '/queue?status=en_atencion_recepcion', expect.anything())
  })

  it('sin edit-patient el formulario es de solo lectura; con edit-patient se edita', async () => {
    const readOnly = await mountPage(ReceptionPage, allExcept(TAGS.reception.editPatient))
    await selectCard(readOnly)
    expect(readOnly.find('fieldset').element.disabled).toBe(true)
    expect(readOnly.text()).toContain('Solo lectura')
    expect(readOnly.text()).toContain('Editar datos del paciente y la orden')
    const editable = await mountPage(ReceptionPage, ALL)
    await selectCard(editable)
    expect(editable.find('fieldset').element.disabled).toBe(false)
    expect(editable.text()).not.toContain('Solo lectura')
  })

  it('"Cerrar y generar orden" exige close-reception y "Devolver" exige return', async () => {
    const without = await mountPage(ReceptionPage, allExcept(TAGS.reception.closeReception, TAGS.reception.return))
    await selectCard(without)
    expect(btn(without, 'Cerrar y generar orden')).toBeNull()
    expect(btn(without, 'Devolver a pre-recepción')).toBeNull()
    const full = await mountPage(ReceptionPage, ALL)
    await selectCard(full)
    expect(btn(full, 'Cerrar y generar orden')).not.toBeNull()
    expect(btn(full, 'Devolver a pre-recepción')).not.toBeNull()
  })
})

describe('impresión de etiquetas', () => {
  beforeEach(() => {
    fake.routes['GET /queue'] = [entry('en_espera_impresion')]
    fake.routes['POST /orders/by-entry/e1/samples'] = order()
  })

  it('sin print se ven tubos y etiquetas pero no hay botones de imprimir ni descargar', async () => {
    const wrapper = await mountPage(ImpresionPage, allExcept(TAGS.labelPrinting.print))
    await selectCard(wrapper)
    expect(wrapper.text()).toContain('Tubo rojo')
    expect(btn(wrapper, 'Descargar ZPL')).toBeNull()
    expect(btn(wrapper, 'Imprimir etiquetas y asignar')).toBeNull()
  })

  it('imprimir envía el profesional (sin actor) y abre el PDF con petición firmada (blob)', async () => {
    const pdf = new Blob(['%PDF'])
    fake.routes['POST /orders/by-entry/e1/print-labels'] = { ok: true }
    fake.routes['GET /orders/by-entry/e1/labels.pdf'] = pdf
    const wrapper = await mountPage(ImpresionPage, ALL)
    await selectCard(wrapper)
    const select = wrapper.find('select')
    ;(select.element as HTMLSelectElement).value = STAFF.id
    await select.trigger('change')
    await flushAll()
    btn(wrapper, 'Imprimir etiquetas y asignar')!.click()
    await flushAll()
    expect(fake.bodies('POST', '/orders/by-entry/e1/print-labels')).toEqual([
      { professional_id: 'st1', professional_name: 'Marta Ruiz' }
    ])
    expect(fake.requests).toHaveBeenCalledWith('GET', '/orders/by-entry/e1/labels.pdf', { responseType: 'blob' })
    expect(files.showPdf).toHaveBeenCalledWith(pdf, 'etiquetas-2610-0001.pdf')
  })

  it('"Descargar ZPL" pide el archivo firmado y lo guarda; un fallo es legible', async () => {
    const zpl = new Blob(['^XA'])
    fake.routes['GET /orders/by-entry/e1/labels.zpl'] = zpl
    const wrapper = await mountPage(ImpresionPage, ALL)
    await selectCard(wrapper)
    btn(wrapper, 'Descargar ZPL')!.click()
    await flushAll()
    expect(fake.requests).toHaveBeenCalledWith('GET', '/orders/by-entry/e1/labels.zpl', { responseType: 'blob' })
    expect(files.saveFile).toHaveBeenCalledWith(zpl, 'etiquetas-2610-0001.zpl')
  })
})

describe('toma de muestras', () => {
  beforeEach(() => {
    fake.routes['GET /queue'] = [
      entry('en_espera_toma_muestras', 'w1', { assigned_professional_id: 'st1' }),
      entry('en_atencion_toma_muestras', 'e1', { assigned_professional_id: 'st1' })
    ]
    fake.routes['GET /orders/by-entry/e1'] = order()
  })

  async function open(tags: string[]) {
    localStorage.setItem('incubus.professional', 'st1')
    const wrapper = await mountPage(SamplingPage, tags)
    await selectCard(wrapper)
    return wrapper
  }

  it('"Tomar paciente" solo con claim y el cuerpo solo lleva el profesional', async () => {
    expect(btn(await open(allExcept(TAGS.sampling.claim)), 'Tomar paciente')).toBeNull()
    const wrapper = await open(ALL)
    fake.routes['POST /queue/w1/claim'] = entry('en_atencion_toma_muestras', 'w1')
    btn(wrapper, 'Tomar paciente')!.click()
    await flushAll()
    expect(fake.bodies('POST', '/queue/w1/claim')).toEqual([{ professional_id: 'st1' }])
  })

  it('marcar tubos exige collect; sin él la verificación y los tubos son de solo lectura', async () => {
    const without = await open(allExcept(TAGS.sampling.collect))
    expect(btn(without, 'Marcar como tomado')).toBeNull()
    expect(without.find('fieldset').element.disabled).toBe(true)
    expect(without.text()).toContain('Marcar tubos tomados')
    const full = await open(ALL)
    fake.routes['POST /orders/samples/s1/collect'] = sample('s1', { collected_at: '2026-10-20T10:30:00Z' })
    btn(full, 'Marcar como tomado')!.click()
    await flushAll()
    expect(fake.requests).toHaveBeenCalledWith('POST', '/orders/samples/s1/collect', { method: 'POST' })
  })

  it('finalizar exige finish y devolver exige return', async () => {
    const without = await open(allExcept(TAGS.sampling.finish, TAGS.sampling.return))
    expect(btn(without, 'Finalizar toma')).toBeNull()
    expect(btn(without, 'Devolver a espera')).toBeNull()
    const full = await open(ALL)
    expect(btn(full, 'Finalizar toma')).not.toBeNull()
    expect(btn(full, 'Devolver a espera')).not.toBeNull()
  })

  it('finalizar no envía actor', async () => {
    fake.routes['GET /orders/by-entry/e1'] = order([sample('s1', { collected_at: '2026-10-20T10:30:00Z' })])
    const wrapper = await open(ALL)
    btn(wrapper, 'Finalizar toma')!.click()
    await flushAll()
    expect(fake.requests).toHaveBeenCalledWith('POST', '/queue/e1/finish-sampling', { method: 'POST' })
  })
})

describe('recepción en laboratorio', () => {
  it('recibir y deshacer exigen cada uno su tag', async () => {
    fake.routes['GET /lab/reception'] = [labOrder(false)]
    const pending = await mountPage(LabReceptionPage, allExcept(TAGS.labReception.receive))
    await pending.find('aside button').trigger('click')
    await flushAll()
    expect(btn(pending, 'Marcar recibido')).toBeNull()
    expect(btn(pending, 'Recibir todos los tubos')).toBeNull()

    fake.routes['GET /lab/reception'] = [labOrder(true)]
    const received = await mountPage(LabReceptionPage, allExcept(TAGS.labReception.unreceive))
    await received.find('aside button').trigger('click')
    await flushAll()
    expect(btn(received, 'Deshacer')).toBeNull()
  })

  it('recibir un tubo no envía actor', async () => {
    fake.routes['GET /lab/reception'] = [labOrder(false)]
    fake.routes['POST /orders/samples/s1/receive'] = { entry_status: 'toma_finalizada' }
    const wrapper = await mountPage(LabReceptionPage, ALL)
    await wrapper.find('aside button').trigger('click')
    await flushAll()
    btn(wrapper, 'Marcar recibido')!.click()
    await flushAll()
    expect(fake.requests).toHaveBeenCalledWith('POST', '/orders/samples/s1/receive', { method: 'POST' })
  })
})

describe('resultados', () => {
  it('la acción de la lista es "Validar" con enter o validate, y "Ver" con solo view', async () => {
    localStorage.setItem('incubus.validator', 'v1')
    fake.routes['GET /catalog/validators'] = [{ id: 'v1', name: 'Dr. Pérez', areas: [] }]
    fake.routes['GET /results/queue'] = [
      {
        entry_id: 'e1',
        order_number: '2610-0001',
        patient_name: 'Luisa Gómez',
        document: 'CC 1001',
        tests: [{ order_test_id: 't1', code: 'GLU', name: 'Glucosa', area_code: 'QUI', validation_status: 'pending' }]
      }
    ]
    expect(buttonTexts((await mountPage(ResultsPage, [TAGS.results.view])).element)).toContain('Ver')
    expect(buttonTexts((await mountPage(ResultsPage, [TAGS.results.view, TAGS.results.enter])).element)).toContain('Validar')
  })
})

describe('formulario de un examen', () => {
  const DETAIL = {
    order_test_id: 't1',
    order_number: '2610-0001',
    code: 'GLU',
    name: 'Glucosa',
    area_code: 'QUI',
    validation_status: 'pending',
    validated_by: null,
    patient: { name: 'Luisa Gómez', document_type: 'CC', document_number: '1001', sex: 'F', age_years: 36 },
    results: [
      {
        code: 'GLU', name: 'Glucosa', section: null, result_type: 'numeric', unit: 'mg/dL', decimals: 0, options: [],
        formula: null, is_required: true, is_reportable: true, reference: null, range: null, value: 90, flag: null
      }
    ]
  }

  async function mountForm(tags: string[]) {
    fake.routes['GET /results/tests/t1'] = DETAIL
    signInWith(tags)
    const wrapper = await mountSuspended(ExamValidationForm, {
      props: { orderTestId: 't1', professionalId: 'v1', professionalName: 'Dr. Pérez' }
    })
    await flushAll()
    return wrapper as unknown as Mounted
  }

  it('enter da "Guardar borrador" y validate da "Finalizar validación", cada uno por su tag', async () => {
    const onlyEnter = await mountForm([TAGS.results.view, TAGS.results.enter])
    expect(btn(onlyEnter, 'Guardar borrador')).not.toBeNull()
    expect(btn(onlyEnter, 'Finalizar validación de Glucosa')).toBeNull()
    const onlyValidate = await mountForm([TAGS.results.view, TAGS.results.validate])
    expect(btn(onlyValidate, 'Guardar borrador')).toBeNull()
    expect(btn(onlyValidate, 'Finalizar validación de Glucosa')).not.toBeNull()
  })

  it('con solo view es de solo lectura: campos deshabilitados y sin botones', async () => {
    const wrapper = await mountForm([TAGS.results.view])
    expect(wrapper.text()).toContain('Solo lectura')
    expect(wrapper.text()).toContain('Capturar resultados')
    expect(wrapper.text()).toContain('Validar resultados')
    expect(btn(wrapper, 'Guardar borrador')).toBeNull()
    expect(wrapper.find('input').element.disabled).toBe(true)
  })

  it('validar envía el profesional (dato de negocio) y los valores, sin actor', async () => {
    fake.routes['POST /results/tests/t1/validate'] = { ...DETAIL, validation_status: 'validated', order_finalized: false }
    const wrapper = await mountForm(ALL)
    btn(wrapper, 'Finalizar validación de Glucosa')!.click()
    await flushAll()
    expect(fake.bodies('POST', '/results/tests/t1/validate')).toEqual([
      { professional_id: 'v1', professional_name: 'Dr. Pérez', values: { GLU: 90 } }
    ])
  })
})
