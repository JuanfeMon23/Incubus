import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { findButton, flushAll } from '~/testing/dom'
import { entry, order, sample } from '~/testing/fixtures'
import { signInWith } from '#leo-client/testing/session'
import { ALL, allExcept } from '~/testing/session'
import { TAGS } from '~/utils/tags'
import QueueHistoryButton from '../components/QueueHistoryButton.vue'
import QueueHistoryModal from '../components/QueueHistoryModal.vue'
import ReceptionPage from './recepcion.vue'
import SamplingPage from './toma-muestras.vue'
import ExamValidationForm from '../components/ExamValidationForm.vue'

const fake = await vi.hoisted(async () => (await import('~/testing/fakeApi')).createFakeApi())
mockNuxtImport('useLeoAppApi', () => () => fake.client)
mockNuxtImport('useQueueSocket', () => () => ({
  connected: { value: true },
  reconnecting: { value: false },
  error: { value: '' },
  subscribe: () => () => {},
  open: () => {},
  close: () => {}
}))

enableAutoUnmount(afterEach)

// La sesión de prueba es `u1` (Ana Pérez).
const ME = 'u1'
const OTHER = 'u2'

beforeEach(() => {
  fake.reset()
  document.body.innerHTML = ''
  fake.routes['GET /catalog/staff'] = [{ id: 'st1', name: 'Marta Ruiz', job_title: null }]
  fake.routes['GET /orders/by-entry/e1'] = order([sample('s1', { collected_at: '2026-10-20T10:30:00Z' })])
})

async function openSampling(tags: string[], claimedBy: string | null, claimedUserId: string | null) {
  fake.routes['GET /queue'] = [
    entry('en_atencion_toma_muestras', 'e1', {
      assigned_professional_id: 'st1',
      claimed_by: claimedBy,
      claimed_by_user_id: claimedUserId
    })
  ]
  localStorage.setItem('incubus.professional', 'st1')
  signInWith(tags)
  const wrapper = await mountSuspended(SamplingPage)
  await flushAll()
  await wrapper.find('article[role="button"]').trigger('click')
  await flushAll()
  return wrapper
}
const btn = (w: { element: Element }, text: string) => findButton(w.element, text)

describe('toma de muestras: propiedad del turno', () => {
  it('las verificaciones de precondiciones se deshabilitan para quien no es dueño ni supervisor', async () => {
    const withPre = order([sample('s1')])
    withPre.preconditions = [
      { key: 'ayuno', category: 'x', name: 'Ayuno', duration_value: 8, duration_unit: 'h', patient_instructions: null, source_test_codes: ['GLU'] }
    ]
    fake.routes['GET /orders/by-entry/e1'] = withPre
    const other = await openSampling(allExcept(TAGS.sampling.supervise), 'Luis Gómez', OTHER)
    expect(btn(other, 'Cumple')!.disabled).toBe(true)
    expect(btn(other, 'No cumple')!.disabled).toBe(true)
    expect(btn(other, 'Cumple')!.getAttribute('title')).toContain('Luis Gómez')
    const mine = await openSampling(allExcept(TAGS.sampling.supervise), 'Ana Pérez', ME)
    expect(btn(mine, 'Cumple')!.disabled).toBe(false)
  })


  it('muestra "Tomado por" con el nombre', async () => {
    const w = await openSampling(ALL, 'Ana Pérez', ME)
    expect(w.text()).toContain('Tomado por Ana Pérez')
  })

  it('el dueño puede devolver, finalizar y marcar tubos', async () => {
    const w = await openSampling(allExcept(TAGS.sampling.supervise), 'Ana Pérez', ME)
    expect(btn(w, 'Devolver a espera')!.disabled).toBe(false)
    expect(btn(w, 'Finalizar toma')!.disabled).toBe(false)
    expect(btn(w, 'Deshacer toma')!.disabled).toBe(false)
  })

  it('otra persona ve las acciones deshabilitadas, con aviso legible', async () => {
    const w = await openSampling(allExcept(TAGS.sampling.supervise), 'Luis Gómez', OTHER)
    const aviso = 'Este turno lo tomó Luis Gómez. Solo esa persona (o un supervisor) puede'
    expect(w.text()).toContain(aviso)
    for (const text of ['Devolver a espera', 'Finalizar toma', 'Deshacer toma']) {
      const b = btn(w, text)!
      expect(b.disabled).toBe(true)
      expect(b.getAttribute('title')).toContain('Luis Gómez')
    }
  })

  it('un supervisor puede actuar en turnos ajenos', async () => {
    const w = await openSampling(ALL, 'Luis Gómez', OTHER)
    expect(btn(w, 'Devolver a espera')!.disabled).toBe(false)
    expect(btn(w, 'Finalizar toma')!.disabled).toBe(false)
    expect(btn(w, 'Deshacer toma')!.disabled).toBe(false)
  })

  it('turno legado (sin id de dueño) no se restringe', async () => {
    const w = await openSampling(allExcept(TAGS.sampling.supervise), 'Luis Gómez', null)
    expect(btn(w, 'Devolver a espera')!.disabled).toBe(false)
    expect(btn(w, 'Finalizar toma')!.disabled).toBe(false)
  })

  it('un 403 not_turn_owner muestra el mensaje del backend y refresca la lista', async () => {
    const message = 'Este turno lo tomó Luis Gómez. Solo esa persona (o un supervisor) puede finalizarlo.'
    // El front cree que es suyo (turno legado), pero el servidor sabe quién es el dueño.
    const w = await openSampling(allExcept(TAGS.sampling.supervise), 'Luis Gómez', null)
    fake.routes['POST /queue/e1/finish-sampling'] = () => {
      throw new LeoApiError(403, 'not_turn_owner', message, { claimed_by: 'Luis Gómez' })
    }
    const before = fake.requests.mock.calls.filter(([m, p]) => m === 'GET' && p.startsWith('/queue')).length
    btn(w, 'Finalizar toma')!.click()
    await flushAll()
    expect(w.text()).toContain(message)
    const after = fake.requests.mock.calls.filter(([m, p]) => m === 'GET' && p.startsWith('/queue')).length
    expect(after).toBeGreaterThan(before)
  })
})

const HISTORY = [
  {
    from_status: null,
    to_status: 'pre_recepcion',
    kind: 'enter',
    changed_at: '2026-10-20T14:00:00Z',
    actor: 'Luis Gómez',
    actor_user_id: OTHER,
    note: null,
    removal_reason_id: null,
    return_reason_id: null
  },
  {
    from_status: 'en_atencion_toma_muestras',
    to_status: 'en_espera_toma_muestras',
    kind: 'return',
    changed_at: '2026-10-20T15:00:00Z',
    actor: 'Ana Pérez',
    actor_user_id: ME,
    note: 'Paciente sin ayuno',
    removal_reason_id: null,
    return_reason_id: 'r1'
  }
]

describe('historial del turno', () => {
  const mountModal = async () => {
    signInWith(ALL)
    const w = await mountSuspended(QueueHistoryModal, { props: { entryId: 'e1' } })
    await flushAll()
    return w
  }

  it('muestra la línea de tiempo: acción, etapas, motivo y quién ("Tú" para el usuario actual)', async () => {
    fake.routes['GET /queue/e1/history'] = HISTORY
    await mountModal()
    const text = document.body.textContent ?? ''
    expect(text).toContain('Ingreso a la cola')
    expect(text).toContain('Luis Gómez')
    expect(text).toContain('Devolución')
    expect(text).toContain('En atención de toma de muestras → Espera de toma de muestras')
    expect(text).toContain('Motivo: Paciente sin ayuno')
    expect(text).toContain('Tú')
    expect(text).not.toContain('Ana Pérez')
  })

  it('muestra el nombre del motivo; sin nombre cae a la nota y nunca el id', async () => {
    fake.routes['GET /queue/e1/history'] = [
      { ...HISTORY[1], return_reason_name: 'Sin ayuno', note: 'Comió a las 8' },
      { ...HISTORY[1], kind: 'remove', return_reason_id: null, removal_reason_id: 'rem-77', note: 'Se fue sin avisar' }
    ]
    await mountModal()
    const text = document.body.textContent ?? ''
    expect(text).toContain('Motivo: Sin ayuno')
    expect(text).toContain('Nota: Comió a las 8')
    expect(text).toContain('Motivo: Se fue sin avisar')
    expect(text).not.toContain('rem-77')
  })

  it('estado vacío', async () => {
    fake.routes['GET /queue/e1/history'] = []
    await mountModal()
    expect(document.body.textContent).toContain('aún no tiene movimientos')
  })

  it('error legible, no la respuesta cruda', async () => {
    fake.routes['GET /queue/e1/history'] = () => {
      throw new LeoApiError(404, 'not_found', 'No se encontró el turno.')
    }
    await mountModal()
    expect(document.body.textContent).toContain('No se encontró el turno.')
  })
})

describe('botón Historial', () => {
  it('aparece con el view de alguna etapa y abre el historial', async () => {
    fake.routes['GET /queue/e1/history'] = HISTORY
    signInWith([TAGS.results.view])
    const w = await mountSuspended(QueueHistoryButton, { props: { entryId: 'e1' } })
    await flushAll()
    btn(w, 'Historial')!.click()
    await flushAll()
    expect(fake.requests).toHaveBeenCalledWith('GET', '/queue/e1/history', expect.anything())
    expect(document.body.textContent).toContain('Historial del turno')
  })

  it('sin ningún view no se muestra', async () => {
    signInWith([TAGS.preReception.enqueue, TAGS.sampling.supervise])
    const w = await mountSuspended(QueueHistoryButton, { props: { entryId: 'e1' } })
    await flushAll()
    expect(w.text()).not.toContain('Historial')
  })
})

describe('recepción: propiedad del turno', () => {
  type Claim = { claimed_by: string | null; claimed_by_user_id: string | null }
  async function openReception(tags: string[], claim: Claim, extra: Record<string, unknown> = {}) {
    fake.routes['GET /queue'] = [entry('en_atencion_recepcion', 'e1', { ...claim, ...extra })]
    signInWith(tags)
    const w = await mountSuspended(ReceptionPage)
    await flushAll()
    await w.find('article[role="button"]').trigger('click')
    await flushAll()
    return w
  }
  const OTHERS: Claim = { claimed_by: 'Luis Gómez', claimed_by_user_id: OTHER }
  const noSupervise = allExcept(TAGS.reception.supervise)

  it('el dueño ve "Atiende: <nombre>" y todo habilitado', async () => {
    const w = await openReception(noSupervise, { claimed_by: 'Ana Pérez', claimed_by_user_id: ME })
    expect(w.text()).toContain('Atiende: Ana Pérez')
    expect(w.find('fieldset').element.disabled).toBe(false)
    expect(btn(w, 'Devolver a pre-recepción')!.disabled).toBe(false)
  })

  it('otra persona: formulario y acciones deshabilitados con aviso legible', async () => {
    const w = await openReception(noSupervise, OTHERS)
    expect(w.text()).toContain('Este turno lo tomó Luis Gómez. Solo esa persona (o un supervisor) puede')
    expect(w.find('fieldset').element.disabled).toBe(true)
    for (const text of ['Devolver a pre-recepción', 'Cerrar y generar orden']) {
      const b = btn(w, text)!
      expect(b.disabled).toBe(true)
      expect(b.getAttribute('title')).toContain('Luis Gómez')
    }
  })

  it('un supervisor de recepción actúa en turnos ajenos; el de toma no', async () => {
    const sup = await openReception(ALL, OTHERS)
    expect(sup.find('fieldset').element.disabled).toBe(false)
    expect(btn(sup, 'Devolver a pre-recepción')!.disabled).toBe(false)
    const samplingSup = await openReception(allExcept(TAGS.reception.supervise), OTHERS)
    expect(btn(samplingSup, 'Devolver a pre-recepción')!.disabled).toBe(true)
  })

  it('turno legado (sin id de dueño) no se restringe', async () => {
    const w = await openReception(noSupervise, { claimed_by: 'Luis Gómez', claimed_by_user_id: null })
    expect(w.find('fieldset').element.disabled).toBe(false)
    expect(btn(w, 'Devolver a pre-recepción')!.disabled).toBe(false)
  })

  it('al cerrar abre el comprobante con el código de activación y lo descarta al cerrarlo', async () => {
    fake.routes['GET /catalog/tests'] = [{ code: 'GLU', name: 'Glucosa', abbreviation: null }]
    fake.routes['POST /orders/preview'] = { preconditions: [] }
    fake.routes['POST /orders/close-reception/e1'] = {
      order_number: '2610-0001', order_id: 'o1', activation_code: 'ABCDE-FGHJK'
    }
    const w = await openReception(noSupervise, { claimed_by: 'Ana Pérez', claimed_by_user_id: ME }, { draft: { test_codes: ['GLU'] } })
    btn(w, 'Cerrar y generar orden')!.click()
    await flushAll()
    expect(document.body.textContent).toContain('ABCDE-FGHJK')
    expect(JSON.stringify({ ...localStorage })).not.toContain('ABCDE-FGHJK')
    findButton(document.body, 'Cerrar')!.click()
    await flushAll()
    expect(document.body.textContent).not.toContain('ABCDE-FGHJK')
  })

  it('un 403 not_turn_owner al cerrar muestra el mensaje del backend y refresca la lista', async () => {
    const message = 'Este turno lo tomó Luis Gómez. Solo esa persona (o un supervisor) puede cerrar la recepción.'
    fake.routes['GET /catalog/tests'] = [{ code: 'GLU', name: 'Glucosa', abbreviation: null }]
    fake.routes['POST /orders/preview'] = { preconditions: [] }
    fake.routes['POST /orders/close-reception/e1'] = () => {
      throw new LeoApiError(403, 'not_turn_owner', message, { claimed_by: 'Luis Gómez' })
    }
    // El front cree que es suyo (turno legado), pero el servidor sabe quién es el dueño.
    const w = await openReception(noSupervise, { claimed_by: 'Luis Gómez', claimed_by_user_id: null }, { draft: { test_codes: ['GLU'] } })
    const before = fake.requests.mock.calls.filter(([m, p]) => m === 'GET' && p.startsWith('/queue')).length
    btn(w, 'Cerrar y generar orden')!.click()
    await flushAll()
    expect(w.text()).toContain(message)
    const after = fake.requests.mock.calls.filter(([m, p]) => m === 'GET' && p.startsWith('/queue')).length
    expect(after).toBeGreaterThan(before)
  })
})

describe('resultados: autoría', () => {
  const row = (code: string, name: string, extra: object) => ({
    code, name, section: null, result_type: 'numeric', unit: 'mg/dL', decimals: 0, options: [], formula: null,
    is_required: true, is_reportable: true, reference: null, range: null, value: 90, flag: null, ...extra
  })
  const DETAIL = {
    order_test_id: 't1', order_number: '2610-0001', code: 'GLU', name: 'Glucosa', area_code: 'QUI',
    validation_status: 'validated', validated_by: 'Dra. Mora', validated_by_user_id: ME,
    patient: { name: 'Luisa Gómez', document_type: 'CC', document_number: '1001', sex: 'F', age_years: 36 },
    results: [
      row('GLU', 'Glucosa', { entered_by: 'Ana Pérez', entered_by_user_id: ME }),
      row('COL', 'Colesterol', { entered_by: 'Luis Gómez', entered_by_user_id: OTHER })
    ]
  }
  it('muestra "Capturado por" ("Tú" para el usuario actual) y la validación', async () => {
    fake.routes['GET /results/tests/t1'] = DETAIL
    signInWith(ALL)
    const w = await mountSuspended(ExamValidationForm, {
      props: { orderTestId: 't1', professionalId: 'v1', professionalName: 'Dr. Pérez' }
    })
    await flushAll()
    const text = w.text()
    expect(text).toContain('Capturado por Tú')
    expect(text).toContain('Capturado por Luis Gómez')
    expect(text).toContain('Validado por Dra. Mora (profesional)')
    expect(text).toContain('Validación ejecutada por Tú')
  })
})
