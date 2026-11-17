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
  /** Suma de lotes no merma; la API vieja puede no mandarlo. */
  valor_inventario_mxn?: number
}

/** Configuración editable de una cámara (`POST` y `PATCH /camaras`). */
export interface CamaraCreacion {
  nombre: string
  rango_min_c: number
  rango_max_c: number
  min_para_riesgo: number
  min_para_merma: number
}

/** Sensor de `GET /sensores`; nunca incluye `token_hash`. */
export interface Sensor {
  id: string
  camara_id: number
  camara_nombre: string
  activo: boolean
  /** ISO 8601 de la última lectura, o null si nunca envió. */
  ultima_lectura: string | null
}

/** Respuesta de alta/rotación: el token en claro solo se muestra una vez. */
export interface SensorConToken {
  sensor: Sensor
  token: string
}

export interface Kpis {
  pct_tiempo_en_rango_24h: number
  alertas_activas: number
  tiempo_respuesta_promedio_min: number
  valor_en_riesgo_mxn: number
  merma_hoy_mxn: number
  merma_mes_mxn: number
}

/** Valores conocidos de severidad; el backend puede guardar otros strings. */
export type SeveridadSeguridad = 'low' | 'medium' | 'high' | 'critical'

/** Acciones conocidas que ejecuta el detector SIEM. */
export type AccionSeguridad =
  'bloquear_ip' | 'revocar_token' | 'marcar_lecturas'

export interface AlertaSeguridad {
  id: number
  /** `id` de la regla Sigma que la disparó. */
  regla_id: string
  /** Título corto de la regla. */
  regla: string
  /** String libre del backend; el panel usa “Desconocida” si no la conoce. */
  severidad: string
  ts: string
  ip_origen: string | null
  /** Conteos, sensor y lecturas involucradas. */
  detalle: Record<string, unknown>
  /** String libre del backend; el panel usa “Sin acción” si no la conoce. */
  accion: string
  /** Descripción opcional enviada por el backend; fuente principal si existe. */
  descripcion?: string
}

/** Alerta operativa de `GET /alertas` y de los eventos del stream. */
export interface AlertaOperativa {
  id: number
  camara_id: number
  /** `temperatura` o `puerta`; el backend guarda string. */
  tipo: string
  abierta_en: string
  cerrada_en: string | null
  /** Usuario del seed (`jefe`) mientras no hay auth/JWT. */
  atendida_por: number | null
  temperatura_max_c: number | null
  sms_enviados: number
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

/** Unidades válidas de un lote de inventario. */
export type UnidadLote = 'kg' | 'l' | 'pz'

/** Estados del lote; `merma` es historial y no se edita ni se borra. */
export type EstadoLote = 'ok' | 'en_riesgo' | 'merma'

/** Fila de `GET /lotes` y respuesta de las mutaciones de inventario. */
export interface Lote {
  id: number
  producto: string
  camara_id: number
  cantidad: number
  unidad: UnidadLote
  costo_total_mxn: number
  /** Fecha ISO `YYYY-MM-DD`. */
  caducidad: string
  estado: EstadoLote
  /** ISO 8601 cuando el lote pasó a merma. */
  merma_en: string | null
}

/** Body de `POST /lotes` y del `PATCH` de inventario. */
export interface LoteCreacion {
  producto: string
  camara_id: number
  cantidad: number
  unidad: UnidadLote
  costo_total_mxn: number
  caducidad: string
}

/** Filtros opcionales de `GET /lotes`. */
export interface FiltrosLotes {
  camara_id?: number
  estado?: EstadoLote
}
