import type {
  AlertaOperativa,
  AlertaSeguridad,
  Camara,
  Health,
  Kpis,
  Lectura,
} from '../types'
import { esObjeto } from '../lib/validacion'
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

/** Alertas operativas que siguen abiertas (`GET /alertas?activas=true`). */
export async function obtenerAlertasActivas(
  senal?: AbortSignal,
): Promise<AlertaOperativa[]> {
  const datos = await pedir<unknown>('/alertas?activas=true&limite=200', {
    signal: senal,
  })

  if (!Array.isArray(datos)) {
    throw new Error(
      'La API devolvió un formato inesperado para las alertas activas.',
    )
  }

  return datos
    .map(normalizarAlertaOperativa)
    .filter((alerta): alerta is AlertaOperativa => alerta !== null)
}

/**
 * Marca una alerta como atendida. El backend responde 409 si ya está cerrada;
 * el hook usa ese status para refrescar la lista en vez de romper.
 */
export async function atenderAlerta(
  id: number,
  nota?: string,
): Promise<AlertaOperativa> {
  const datos = await pedir<unknown>(`/alertas/${id}/atender`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nota: nota ?? null }),
  })

  const alerta = normalizarAlertaOperativa(datos)
  if (!alerta) {
    throw new Error('La API devolvió una alerta operativa inválida.')
  }
  return alerta
}

function normalizarAlertaOperativa(valor: unknown): AlertaOperativa | null {
  if (!esObjeto(valor)) {
    return null
  }

  const {
    id,
    camara_id: camaraId,
    tipo,
    abierta_en: abiertaEn,
    cerrada_en: cerradaEn,
    atendida_por: atendidaPor,
    temperatura_max_c: temperaturaMax,
    sms_enviados: smsEnviados,
  } = valor

  if (
    typeof id !== 'number' ||
    typeof camaraId !== 'number' ||
    typeof tipo !== 'string' ||
    typeof abiertaEn !== 'string'
  ) {
    return null
  }

  return {
    id,
    camara_id: camaraId,
    tipo,
    abierta_en: abiertaEn,
    cerrada_en: typeof cerradaEn === 'string' ? cerradaEn : null,
    atendida_por: typeof atendidaPor === 'number' ? atendidaPor : null,
    temperatura_max_c:
      typeof temperaturaMax === 'number' ? temperaturaMax : null,
    sms_enviados: typeof smsEnviados === 'number' ? smsEnviados : 0,
  }
}

/**
 * Alertas del detector SIEM.
 *
 * El backend guarda `severidad` y `accion` como strings libres: se conservan
 * tal cual y el panel decide la etiqueta (con fallback). Si la respuesta no
 * es un arreglo se lanza para que el hook conserve las alertas anteriores.
 */
export async function obtenerAlertasSeguridad(
  senal?: AbortSignal,
): Promise<AlertaSeguridad[]> {
  const datos = await pedir<unknown>('/seguridad/alertas', { signal: senal })

  if (!Array.isArray(datos)) {
    throw new Error(
      'La API devolvió un formato inesperado para las alertas de seguridad.',
    )
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
    typeof severidad !== 'string' ||
    typeof ts !== 'string' ||
    !esObjeto(detalle) ||
    typeof accion !== 'string'
  ) {
    return null
  }

  return {
    id,
    regla_id: reglaId,
    regla,
    severidad,
    ts,
    // El contrato permite null; una clave ausente también se normaliza a null.
    ip_origen: typeof ipOrigen === 'string' ? ipOrigen : null,
    detalle,
    accion,
  }
}
