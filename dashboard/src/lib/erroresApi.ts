import { ErrorApi } from '../api/client'

export type ContextoError = 'camara' | 'sensor'

const MENSAJE_422: Record<ContextoError, string> = {
  camara: 'Revisa el nombre, el rango y los minutos.',
  sensor: 'Revisa los datos del sensor.',
}

/**
 * Mensaje accionable para un fallo de la API de administración.
 *
 * El `detail` de FastAPI se usa cuando es texto claro o cuando el 422 trae
 * `detail[]` con `msg`; solo se cae al resumen por contexto si no hay detalle.
 */
export function mensajeDeError(
  error: unknown,
  contexto: ContextoError = 'camara',
): string {
  if (error instanceof ErrorApi) {
    if (error.status === 401) {
      return 'Tu sesión expiró. Vuelve a iniciar sesión.'
    }
    if (error.status === 403) {
      return 'Solo el dueño del restaurante puede administrar cámaras y sensores.'
    }
    if (error.status === 404) {
      return error.detalle ?? 'El elemento ya no existe. Actualiza la lista.'
    }
    if (error.status === 409) {
      return (
        error.detalle ?? 'Hay datos asociados que impiden completar la acción.'
      )
    }
    if (error.status === 422) {
      return error.detalle ?? MENSAJE_422[contexto]
    }
    return error.message
  }

  if (error instanceof Error) {
    return error.message
  }
  return 'Ocurrió un error inesperado.'
}
