import { ErrorApi } from '../api/client'

/**
 * Mensaje accionable para un fallo de la API de administración.
 *
 * El `detail` de FastAPI solo se usa cuando es un texto claro (409/404); los
 * 422 traen un arreglo de validación y aquí se resumen en una frase útil.
 */
export function mensajeDeError(error: unknown): string {
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
      return 'Los datos no son válidos. Revisa el nombre, el rango y los minutos.'
    }
    return error.message
  }

  if (error instanceof Error) {
    return error.message
  }
  return 'Ocurrió un error inesperado.'
}
