import type {
  AlertaOperativa,
  AlertaSeguridad,
  Camara,
  CamaraCreacion,
  EstadoCamara,
  Health,
  Kpis,
  Lectura,
  Sensor,
  SensorConToken,
  UltimaLectura,
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

  // Los DELETE responden 204 sin cuerpo; intentar parsear JSON rompería.
  if (respuesta.status === 204) {
    return undefined as T
  }

  return (await respuesta.json()) as T
}

/** Respuesta de `POST /auth/login`. */
export interface RespuestaLogin {
  access_token: string
  token_type: string
  expira_en_segundos: number
}

/** Valida el contrato de sesión de login y registro en un solo lugar. */
function validarRespuestaLogin(datos: unknown): RespuestaLogin {
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

  return validarRespuestaLogin(datos)
}

/**
 * Alta de restaurante y su usuario dueño. Igual que el login, no adjunta un
 * token viejo: el registro es público y devuelve la sesión nueva.
 */
export async function registrar(
  restaurante: string,
  usuario: string,
  password: string,
): Promise<RespuestaLogin> {
  const datos = await pedir<unknown>(
    '/auth/registro',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ restaurante, usuario, password }),
    },
    { sinAuth: true },
  )

  return validarRespuestaLogin(datos)
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
    descripcion,
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
    ...(typeof descripcion === 'string' && descripcion.trim()
      ? { descripcion }
      : {}),
  }
}

/* ------------------------------------------------------------------ */
/* Administración de cámaras y sensores                                */
/* ------------------------------------------------------------------ */

const ESTADOS_CAMARA: readonly EstadoCamara[] = [
  'en_rango',
  'alerta',
  'critica',
]

function esEstadoCamara(valor: unknown): valor is EstadoCamara {
  return (
    typeof valor === 'string' &&
    (ESTADOS_CAMARA as readonly string[]).includes(valor)
  )
}

function normalizarUltimaLectura(valor: unknown): UltimaLectura | null {
  if (!esObjeto(valor)) {
    return null
  }

  const { ts, temperatura_c, humedad_pct, puerta_abierta } = valor
  if (
    typeof ts !== 'string' ||
    typeof temperatura_c !== 'number' ||
    typeof humedad_pct !== 'number' ||
    typeof puerta_abierta !== 'boolean'
  ) {
    return null
  }

  return {
    ts,
    temperatura_c,
    humedad_pct,
    puerta_abierta,
  }
}

function normalizarCamara(valor: unknown): Camara | null {
  if (!esObjeto(valor)) {
    return null
  }

  const {
    id,
    nombre,
    rango_min_c: rangoMin,
    rango_max_c: rangoMax,
    min_para_riesgo: minRiesgo,
    min_para_merma: minMerma,
    estado,
    ultima_lectura: ultimaLectura,
    valor_en_riesgo_mxn: valorRiesgo,
    valor_inventario_mxn: valorInventario,
  } = valor

  if (
    typeof id !== 'number' ||
    !Number.isFinite(id) ||
    typeof nombre !== 'string' ||
    !nombre.trim() ||
    typeof rangoMin !== 'number' ||
    !Number.isFinite(rangoMin) ||
    typeof rangoMax !== 'number' ||
    !Number.isFinite(rangoMax) ||
    typeof minRiesgo !== 'number' ||
    !Number.isFinite(minRiesgo) ||
    typeof minMerma !== 'number' ||
    !Number.isFinite(minMerma) ||
    !esEstadoCamara(estado)
  ) {
    return null
  }

  const lectura =
    ultimaLectura === null ? null : normalizarUltimaLectura(ultimaLectura)
  if (ultimaLectura !== null && lectura === null) {
    return null
  }

  return {
    id,
    nombre,
    rango_min_c: rangoMin,
    rango_max_c: rangoMax,
    min_para_riesgo: minRiesgo,
    min_para_merma: minMerma,
    estado,
    ultima_lectura: lectura,
    valor_en_riesgo_mxn:
      typeof valorRiesgo === 'number' && Number.isFinite(valorRiesgo)
        ? valorRiesgo
        : 0,
    ...(typeof valorInventario === 'number' && Number.isFinite(valorInventario)
      ? { valor_inventario_mxn: valorInventario }
      : {}),
  }
}

function normalizarSensor(valor: unknown): Sensor | null {
  if (!esObjeto(valor)) {
    return null
  }

  const {
    id,
    camara_id: camaraId,
    camara_nombre: camaraNombre,
    activo,
    ultima_lectura: ultimaLectura,
  } = valor

  if (
    typeof id !== 'string' ||
    !id ||
    typeof camaraId !== 'number' ||
    !Number.isFinite(camaraId) ||
    typeof activo !== 'boolean'
  ) {
    return null
  }

  return {
    id,
    camara_id: camaraId,
    camara_nombre: typeof camaraNombre === 'string' ? camaraNombre : '',
    activo,
    ultima_lectura: typeof ultimaLectura === 'string' ? ultimaLectura : null,
  }
}

function normalizarSensorConToken(valor: unknown): SensorConToken {
  if (!esObjeto(valor)) {
    throw new Error('La API devolvió un sensor inválido.')
  }

  const sensor = normalizarSensor(valor.sensor)
  if (!sensor || typeof valor.token !== 'string' || !valor.token) {
    throw new Error('La API devolvió un sensor inválido.')
  }

  return { sensor, token: valor.token }
}

/** `POST /camaras`: crea una cámara en el restaurante del JWT. */
export async function crearCamara(datos: CamaraCreacion): Promise<Camara> {
  const respuesta = await pedir<unknown>('/camaras', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(datos),
  })

  const camara = normalizarCamara(respuesta)
  if (!camara) {
    throw new Error('La API devolvió una cámara inválida.')
  }
  return camara
}

/** `PATCH /camaras/{id}`: solo configuración; la respuesta es la cámara final. */
export async function actualizarCamara(
  id: number,
  datos: Partial<CamaraCreacion>,
): Promise<Camara> {
  const respuesta = await pedir<unknown>(`/camaras/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(datos),
  })

  const camara = normalizarCamara(respuesta)
  if (!camara) {
    throw new Error('La API devolvió una cámara inválida.')
  }
  return camara
}

/** `DELETE /camaras/{id}`: 204, o 409 si tiene sensores, lotes o lecturas. */
export async function eliminarCamara(id: number): Promise<void> {
  await pedir<void>(`/camaras/${id}`, { method: 'DELETE' })
}

/** `GET /sensores`: sensores del restaurante sin `token_hash`. */
export async function listarSensores(): Promise<Sensor[]> {
  const datos = await pedir<unknown>('/sensores')

  if (!Array.isArray(datos)) {
    throw new Error('La API devolvió un formato inesperado para los sensores.')
  }

  return datos
    .map(normalizarSensor)
    .filter((sensor): sensor is Sensor => sensor !== null)
}

/** `POST /camaras/{id}/sensores` sin body: el token se ve una sola vez. */
export async function crearSensor(camaraId: number): Promise<SensorConToken> {
  const datos = await pedir<unknown>(`/camaras/${camaraId}/sensores`, {
    method: 'POST',
  })
  return normalizarSensorConToken(datos)
}

/** `POST /sensores/{id}/rotar-token`: invalida el token anterior. */
export async function rotarTokenSensor(id: string): Promise<SensorConToken> {
  const datos = await pedir<unknown>(`/sensores/${id}/rotar-token`, {
    method: 'POST',
  })
  return normalizarSensorConToken(datos)
}

/** `PATCH /sensores/{id}`: enciende o apaga el sensor. */
export async function actualizarSensor(
  id: string,
  datos: { activo: boolean },
): Promise<Sensor> {
  const respuesta = await pedir<unknown>(`/sensores/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(datos),
  })

  const sensor = normalizarSensor(respuesta)
  if (!sensor) {
    throw new Error('La API devolvió un sensor inválido.')
  }
  return sensor
}

/** `DELETE /sensores/{id}`: 204, o 409 si el sensor ya tiene lecturas. */
export async function eliminarSensor(id: string): Promise<void> {
  await pedir<void>(`/sensores/${id}`, { method: 'DELETE' })
}
