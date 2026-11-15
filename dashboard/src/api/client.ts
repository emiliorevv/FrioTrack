import type {
  AlertaOperativa,
  AlertaSeguridad,
  Camara,
  Health,
  Kpis,
  Lectura,
} from '../types'
import { esObjeto } from '../lib/validacion'
import { getToken, notificarNoAutorizado } from '../auth/token'
import { resolverApiUrl } from './url'

const TIEMPO_LIMITE_MS = 10_000

/** Error HTTP de la API: conserva el status y el `detail` del contrato. */
export class ErrorApi extends Error {
  readonly status: number
  /** Segundos de `Retry-After` en un 429, si el backend lo manda. */
  readonly retryAfterSegundos: number | null
  /** `detail` real del backend; `null` si solo había un status HTTP. */
  readonly detalle: string | null

  constructor(
    mensaje: string,
    status: number,
    retryAfterSegundos: number | null = null,
    detalle: string | null = null,
  ) {
    super(mensaje)
    this.name = 'ErrorApi'
    this.status = status
    this.retryAfterSegundos = retryAfterSegundos
    this.detalle = detalle
  }
}

interface DetalleError {
  mensaje: string
  detalle: string | null
}

async function leerDetalle(respuesta: Response): Promise<DetalleError> {
  try {
    const datos: unknown = await respuesta.json()
    if (
      typeof datos === 'object' &&
      datos !== null &&
      'detail' in datos &&
      typeof datos.detail === 'string' &&
      datos.detail.trim()
    ) {
      return { mensaje: datos.detail, detalle: datos.detail }
    }
  } catch {
    // El cuerpo no era JSON; se usa el status como mensaje.
  }

  const sufijo = respuesta.statusText ? ` ${respuesta.statusText}` : ''
  return {
    mensaje: `La API respondió ${respuesta.status}${sufijo}`,
    detalle: null,
  }
}

/**
 * Petición JSON con la misma base que el stream SSE.
 *
 * Combina el timeout de 10 s con la señal del llamador mediante un
 * `AbortController` manual: `AbortSignal.any` no existe en Safari < 17.4 ni
 * Chrome < 116, que están dentro del target de Vite.
 */
export interface OpcionesPedir {
  /** No adjunta token ni dispara el logout global (login). */
  sinAuth?: boolean
}

export async function pedir<T>(
  ruta: string,
  init?: RequestInit,
  opciones: OpcionesPedir = {},
): Promise<T> {
  const base = resolverApiUrl()
  if (!base) {
    throw new Error(
      'Falta VITE_API_URL: configura la URL de la API para cargar el dashboard.',
    )
  }

  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')

  const token = opciones.sinAuth ? null : getToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  } else {
    headers.delete('Authorization')
  }

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
    if (respuesta.status === 401 && token && getToken() === token) {
      notificarNoAutorizado()
    }

    const { mensaje, detalle } = await leerDetalle(respuesta)
    throw new ErrorApi(
      mensaje,
      respuesta.status,
      leerRetryAfter(respuesta.headers.get('Retry-After')),
      detalle,
    )
  }

  return (await respuesta.json()) as T
}

/** Respuesta de `POST /auth/login`. */
export interface RespuestaLogin {
  access_token: string
  token_type: string
  expira_en_segundos: number
}

/**
 * Login del dashboard. Usa `sinAuth` para no adjuntar un token viejo y para
 * que un 401 de credenciales no dispare el logout global.
 */
export async function iniciarSesion(
  usuario: string,
  password: string,
): Promise<RespuestaLogin> {
  const datos = await pedir<unknown>(
    '/auth/login',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario, password }),
    },
    { sinAuth: true },
  )

  if (
    !esObjeto(datos) ||
    typeof datos.access_token !== 'string' ||
    !datos.access_token ||
    typeof datos.token_type !== 'string' ||
    typeof datos.expira_en_segundos !== 'number'
  ) {
    throw new Error('La API devolvió una sesión inválida.')
  }

  return {
    access_token: datos.access_token,
    token_type: datos.token_type,
    expira_en_segundos: datos.expira_en_segundos,
  }
}

function leerRetryAfter(valor: string | null): number | null {
  const limpio = valor?.trim()
  if (!limpio) {
    return null
  }

  if (/^\d+$/.test(limpio)) {
    const segundos = Number(limpio)
    return Number.isFinite(segundos) && segundos >= 0 ? segundos : null
  }

  const fecha = Date.parse(limpio)
  if (Number.isNaN(fecha)) {
    return null
  }
  return Math.max(0, Math.ceil((fecha - Date.now()) / 1000))
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
