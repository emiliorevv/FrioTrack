import type { Camara, Health, Kpis, Lectura } from '../types'
import { resolverApiUrl } from './url'

const TIEMPO_LIMITE_MS = 10_000

/** Error HTTP de la API: conserva el status y el `detail` del contrato. */
export class ErrorApi extends Error {
  readonly status: number

  constructor(mensaje: string, status: number) {
    super(mensaje)
    this.name = 'ErrorApi'
    this.status = status
  }
}

async function leerDetalle(respuesta: Response): Promise<string> {
  try {
    const datos: unknown = await respuesta.json()
    if (
      typeof datos === 'object' &&
      datos !== null &&
      'detail' in datos &&
      typeof datos.detail === 'string' &&
      datos.detail.trim()
    ) {
      return datos.detail
    }
  } catch {
    // El cuerpo no era JSON; se usa el status como mensaje.
  }

  const sufijo = respuesta.statusText ? ` ${respuesta.statusText}` : ''
  return `La API respondió ${respuesta.status}${sufijo}`
}

/**
 * Petición JSON con la misma base que el stream SSE.
 * El `signal` corta la petición si la API no contesta en 10 s.
 */
async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const base = resolverApiUrl()
  if (!base) {
    throw new Error(
      'Falta VITE_API_URL: configura la URL de la API para cargar el dashboard.',
    )
  }

  let respuesta: Response
  try {
    respuesta = await fetch(`${base}${ruta}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...init?.headers,
      },
      signal: AbortSignal.timeout(TIEMPO_LIMITE_MS),
    })
  } catch (error) {
    if (esTimeout(error)) {
      throw new Error('La API tardó más de 10 s en responder.', {
        cause: error,
      })
    }
    throw error
  }

  if (!respuesta.ok) {
    throw new ErrorApi(await leerDetalle(respuesta), respuesta.status)
  }

  return (await respuesta.json()) as T
}

export function obtenerHealth(): Promise<Health> {
  return pedir<Health>('/health')
}

export function obtenerCamaras(): Promise<Camara[]> {
  return pedir<Camara[]>('/camaras')
}

export function obtenerKpis(): Promise<Kpis> {
  return pedir<Kpis>('/kpis')
}

export function obtenerLecturas(camaraId: number): Promise<Lectura[]> {
  return pedir<Lectura[]>(`/camaras/${camaraId}/lecturas`)
}

/** El `AbortSignal.timeout` rechaza con un DOMException llamado TimeoutError. */
function esTimeout(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    error.name === 'TimeoutError'
  )
}
