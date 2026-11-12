/**
 * Formas tomadas de docs/contrato-api.md.
 * La vista todavía usa datos simulados, pero los campos son los del contrato
 * para que conectar la API sea un cambio de origen de datos, no de componentes.
 */

export type EstadoCamara = 'en_rango' | 'alerta' | 'critica'

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
  ultima_lectura: UltimaLectura
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

/**
 * El contrato define GET /seguridad/alertas pero no la forma de cada fila.
 * Esta es provisional y solo alimenta la vista de demostración del SIEM.
 */
export interface AlertaSeguridad {
  id: number
  ts: string
  titulo: string
  detalle: string
  etiqueta: string
  tono: 'ok' | 'warn'
}

export type FiltroCamaras = 'todas' | EstadoCamara
