/**
 * Formas tomadas de docs/contrato-api.md.
 * La vista todavía usa datos simulados, pero los campos son los del contrato
 * para que conectar la API sea un cambio de origen de datos, no de componentes.
 */

export type EstadoCamara = 'en_rango' | 'alerta' | 'critica'

/** Respuesta de `GET /health`. */
export interface Health {
  ok: boolean
  /** Factor del modo demo; 1 significa tiempo real. */
  escala_tiempo: number
}

/** Fila de `GET /camaras/{id}/lecturas`. */
export interface Lectura {
  id: number
  /** Momento del sensor, ISO 8601. */
  ts: string
  /** Momento en que la API recibió la lectura. */
  recibida_en: string
  temperatura_c: number
  humedad_pct: number
  puerta_abierta: boolean
  /** La marcó el detector de lecturas imposibles. */
  sospechosa: boolean
}

/** Payload del evento `lectura` de `GET /api/stream` (sin id ni recibida_en). */
export interface LecturaStream {
  camara_id: number
  ts: string
  temperatura_c: number
  humedad_pct: number
  puerta_abierta: boolean
  estado_camara: EstadoCamara
}

/** Temperaturas para el sparkline, de la más vieja a la más reciente. */
export type SerieCamara = number[]

/** Punto interno de la serie: conserva `ts` para fusionar HTTP + SSE. */
export interface PuntoSerie {
  ts: string
  valor: number
}

export interface UltimaLectura {
  ts: string
  temperatura_c: number
  humedad_pct: number
  puerta_abierta: boolean
}

export interface Camara {
  id: number
  nombre: string
  rango_min_c: number
  rango_max_c: number
  min_para_riesgo: number
  min_para_merma: number
  estado: EstadoCamara
  /** Nulo cuando la cámara todavía no tiene lecturas (recién sembrada la base). */
  ultima_lectura: UltimaLectura | null
  valor_en_riesgo_mxn: number
}

export interface Kpis {
  pct_tiempo_en_rango_24h: number
  alertas_activas: number
  tiempo_respuesta_promedio_min: number
  valor_en_riesgo_mxn: number
  merma_hoy_mxn: number
  merma_mes_mxn: number
}

/** Misma forma que la tabla `alertas_seguridad` de docs/modelo-datos.md. */
export type SeveridadSeguridad = 'low' | 'medium' | 'high' | 'critical'

/** Acciones de respuesta que ejecuta el detector SIEM. */
export type AccionSeguridad =
  'bloquear_ip' | 'revocar_token' | 'marcar_lecturas'

export interface AlertaSeguridad {
  id: number
  /** `id` de la regla Sigma que la disparó. */
  regla_id: string
  /** Título corto de la regla. */
  regla: string
  severidad: SeveridadSeguridad
  ts: string
  ip_origen: string | null
  /** Conteos, sensor y lecturas involucradas. */
  detalle: Record<string, unknown>
  accion: AccionSeguridad
}

export const TIPOS_NOTIFICACION = [
  'alerta_temperatura',
  'alerta_puerta',
  'merma',
] as const

export type TipoNotificacion = (typeof TIPOS_NOTIFICACION)[number]

/** Payload del evento `notificacion` de `GET /api/stream`. */
export interface Notificacion {
  canal: 'simulado'
  tipo: TipoNotificacion
  camara_id: number
  /** Texto ya formateado por la API; el dashboard solo lo muestra. */
  mensaje: string
  /** ISO 8601. */
  ts: string
  /** Link al dashboard; la vista no navega a ningún lado. */
  url: string
}

export type FiltroCamaras = 'todas' | EstadoCamara
