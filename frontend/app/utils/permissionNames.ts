import { TAGS } from './tags'

/**
 * Nombres legibles de los permisos (tags) de Incubus, para mensajes al
 * usuario ("No tienes permiso para: …"). Se registran en leo-client (plugin permissionNames) para sus mensajes 403. Son los mismos del catálogo que el
 * backend publica en Leo (`backend/app/core/permissions.py`).
 */
export const PERMISSION_NAMES: Record<string, string> = {
  [TAGS.preReception.view]: 'Consultar la cola de pre-recepción',
  [TAGS.preReception.enqueue]: 'Ingresar pacientes a la cola',
  [TAGS.preReception.remove]: 'Retirar pacientes de la cola',
  [TAGS.reception.view]: 'Consultar la recepción de órdenes',
  [TAGS.reception.callNext]: 'Llamar al siguiente paciente',
  [TAGS.reception.editPatient]: 'Editar datos del paciente y la orden',
  [TAGS.reception.closeReception]: 'Cerrar recepción de órdenes',
  [TAGS.reception.return]: 'Devolver pacientes a pre-recepción',
  [TAGS.reception.remove]: 'Retirar pacientes en recepción',
  [TAGS.reception.supervise]: 'Gestionar turnos de otros recepcionistas',
  [TAGS.labelPrinting.view]: 'Consultar la impresión de etiquetas',
  [TAGS.labelPrinting.print]: 'Imprimir etiquetas de tubos',
  [TAGS.sampling.view]: 'Consultar la toma de muestras',
  [TAGS.sampling.claim]: 'Tomar turnos de toma de muestras',
  [TAGS.sampling.collect]: 'Marcar tubos tomados',
  [TAGS.sampling.finish]: 'Finalizar la toma de muestras',
  [TAGS.sampling.return]: 'Devolver pacientes a espera de toma',
  [TAGS.sampling.supervise]: 'Gestionar turnos de otros técnicos',
  [TAGS.labReception.view]: 'Consultar la recepción en laboratorio',
  [TAGS.labReception.receive]: 'Recibir tubos en el laboratorio',
  [TAGS.labReception.unreceive]: 'Deshacer la recepción de tubos',
  [TAGS.results.view]: 'Consultar resultados por validar',
  [TAGS.results.enter]: 'Capturar resultados',
  [TAGS.results.validate]: 'Validar resultados',
  [TAGS.results.trace]: 'Consultar la trazabilidad de una prueba',
  [TAGS.resultsDelivery.view]: 'Consultar resultados entregados',
  [TAGS.queueAdmin.view]: 'Consultar los catálogos de la cola',
  [TAGS.queueAdmin.create]: 'Crear prioridades y motivos de la cola',
  [TAGS.queueAdmin.update]: 'Editar prioridades y motivos de la cola',
  [TAGS.queueAdmin.toggle]: 'Activar y desactivar prioridades y motivos de la cola',
  [TAGS.settings.view]: 'Consultar los ajustes del sistema',
  [TAGS.settings.edit]: 'Modificar los ajustes del sistema',
  [TAGS.settings.editSecurity]: 'Modificar los ajustes de seguridad'
}
