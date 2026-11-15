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
 *
 * Combina el timeout de 10 s con la señal del llamador mediante un
 * `AbortController` manual: `AbortSignal.any` no existe en Safari < 17.4 ni
 * Chrome < 116, que están dentro del target de Vite.
 */
export async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const base = resolverApiUrl()
  if (!base) {
    throw new Error(
      'Falta VITE_API_URL: configura la URL de la API para cargar el dashboard.',
    )
  }

  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')

  const controlador = new AbortController()
  let motivo: 'timeout' | 'llamador' | null = null

  const abortarPorLlamador = () => {
    motivo = 'llamador'
    controlador.abort()
  }

  if (init?.signal) {
    if (init.signal.aborted) {
      abortarPorLlamador()
    } else {
      init.signal.addEventListener('abort', abortarPorLlamador, { once: true })
    }
  }

  const temporizador = setTimeout(() => {
    motivo = 'timeout'
    controlador.abort()
  }, TIEMPO_LIMITE_MS)

  let respuesta: Response
  try {
    respuesta = await fetch(`${base}${ruta}`, {
      ...init,
      headers,
      signal: controlador.signal,
    })
  } catch (error) {
    if (motivo === 'timeout') {
      throw new Error('La API tardó más de 10 s en responder.', {
        cause: error,
      })
    }
    throw error
  } finally {
    clearTimeout(temporizador)
    init?.signal?.removeEventListener('abort', abortarPorLlamador)
  }

  if (!respuesta.ok) {
    throw new ErrorApi(await leerDetalle(respuesta), respuesta.status)
  }

  return (await respuesta.json()) as T
}

export function obtenerHealth(senal?: AbortSignal): Promise<Health> {
  return pedir<Health>('/health', { signal: senal })
}

export function obtenerCamaras(senal?: AbortSignal): Promise<Camara[]> {
  return pedir<Camara[]>('/camaras', { signal: senal })
}

export function obtenerKpis(senal?: AbortSignal): Promise<Kpis> {
  return pedir<Kpis>('/kpis', { signal: senal })
}

export function obtenerLecturas(
  camaraId: number,
  senal?: AbortSignal,
): Promise<Lectura[]> {
  return pedir<Lectura[]>(`/camaras/${camaraId}/lecturas`, { signal: senal })
}
