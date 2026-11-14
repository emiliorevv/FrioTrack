import type {
  AccionSeguridad,
  AlertaSeguridad,
  Camara,
  Health,
  Kpis,
  Lectura,
  SeveridadSeguridad,
} from '../types'
import { esObjeto } from '../lib/sse'
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
 * Respeta la señal del llamador y la combina con un timeout de 10 s, así
 * `AbortController` puede cancelar un refresco superado sin perder el límite.
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

  const senal = init?.signal
    ? AbortSignal.any([init.signal, AbortSignal.timeout(TIEMPO_LIMITE_MS)])
    : AbortSignal.timeout(TIEMPO_LIMITE_MS)

  let respuesta: Response
  try {
    respuesta = await fetch(`${base}${ruta}`, {
      ...init,
      headers,
      signal: senal,
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

/**
 * Alertas del detector SIEM. El backend manda `severidad` y `accion` como
 * strings; se validan antes de tipar y las filas desconocidas se descartan
 * para que el panel nunca reciba un valor fuera del contrato.
 */
export async function obtenerAlertasSeguridad(
  senal?: AbortSignal,
): Promise<AlertaSeguridad[]> {
  const datos = await pedir<unknown>('/seguridad/alertas', { signal: senal })

  if (!Array.isArray(datos)) {
    return []
  }

  return datos
    .map(normalizarAlertaSeguridad)
    .filter((alerta): alerta is AlertaSeguridad => alerta !== null)
}

function normalizarAlertaSeguridad(valor: unknown): AlertaSeguridad | null {
  if (!esObjeto(valor)) {
    return null
  }

  const {
    id,
    regla_id: reglaId,
    regla,
    severidad,
    ts,
    ip_origen: ipOrigen,
    detalle,
    accion,
  } = valor

  if (
    typeof id !== 'number' ||
    typeof reglaId !== 'string' ||
    typeof regla !== 'string' ||
    !esSeveridad(severidad) ||
    typeof ts !== 'string' ||
    (ipOrigen !== null && typeof ipOrigen !== 'string') ||
    !esObjeto(detalle) ||
    !esAccion(accion)
  ) {
    return null
  }

  return {
    id,
    regla_id: reglaId,
    regla,
    severidad,
    ts,
    ip_origen: typeof ipOrigen === 'string' ? ipOrigen : null,
    detalle,
    accion,
  }
}

function esSeveridad(valor: unknown): valor is SeveridadSeguridad {
  return (
    valor === 'low' ||
    valor === 'medium' ||
    valor === 'high' ||
    valor === 'critical'
  )
}

function esAccion(valor: unknown): valor is AccionSeguridad {
  return (
    valor === 'bloquear_ip' ||
    valor === 'revocar_token' ||
    valor === 'marcar_lecturas'
  )
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
