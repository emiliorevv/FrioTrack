import type { AlertaSeguridad, Camara, Kpis } from '../types'

/**
 * Reloj fijo de la demo. Así los textos "hace X" no cambian entre pruebas
 * y la captura del PR no depende del día en que se abra.
 */
export const AHORA_DEMO = new Date('2026-11-12T16:45:00-06:00')

export const actualizadoHaceSegundos = 8

/** Mismo objeto que devuelve GET /kpis. */
export const kpis: Kpis = {
  pct_tiempo_en_rango_24h: 97.3,
  alertas_activas: 1,
  tiempo_respuesta_promedio_min: 6.5,
  valor_en_riesgo_mxn: 4850,
  merma_hoy_mxn: 0,
  merma_mes_mxn: 1720,
}

/** Mismo objeto que devuelve GET /camaras. */
export const camaras: Camara[] = [
  {
    id: 1,
    nombre: 'Pescados y mariscos',
    rango_min_c: 0,
    rango_max_c: 2,
    min_para_riesgo: 10,
    min_para_merma: 60,
    estado: 'critica',
    ultima_lectura: {
      ts: '2026-11-12T16:44:50-06:00',
      temperatura_c: 3.1,
      humedad_pct: 85,
      puerta_abierta: true,
    },
    valor_en_riesgo_mxn: 4850,
  },
  {
    id: 2,
    nombre: 'Carnes y aves',
    rango_min_c: 0,
    rango_max_c: 4,
    min_para_riesgo: 15,
    min_para_merma: 120,
    estado: 'en_rango',
    ultima_lectura: {
      ts: '2026-11-12T16:44:51-06:00',
      temperatura_c: 2.4,
      humedad_pct: 80,
      puerta_abierta: false,
    },
    valor_en_riesgo_mxn: 0,
  },
  {
    id: 3,
    nombre: 'Lácteos',
    rango_min_c: 1,
    rango_max_c: 4,
    min_para_riesgo: 20,
    min_para_merma: 180,
    estado: 'en_rango',
    ultima_lectura: {
      ts: '2026-11-12T16:44:48-06:00',
      temperatura_c: 3.2,
      humedad_pct: 72,
      puerta_abierta: false,
    },
    valor_en_riesgo_mxn: 0,
  },
  {
    id: 4,
    nombre: 'Verduras y frutas',
    rango_min_c: 4,
    rango_max_c: 8,
    min_para_riesgo: 30,
    min_para_merma: 240,
    estado: 'en_rango',
    ultima_lectura: {
      ts: '2026-11-12T16:44:49-06:00',
      temperatura_c: 6.1,
      humedad_pct: 90,
      puerta_abierta: false,
    },
    valor_en_riesgo_mxn: 0,
  },
  {
    id: 5,
    nombre: 'Congelador',
    rango_min_c: -22,
    rango_max_c: -18,
    min_para_riesgo: 20,
    min_para_merma: 120,
    estado: 'en_rango',
    ultima_lectura: {
      ts: '2026-11-12T16:44:52-06:00',
      temperatura_c: -19.4,
      humedad_pct: 65,
      puerta_abierta: false,
    },
    valor_en_riesgo_mxn: 0,
  },
]

/**
 * Series de 24 puntos para los sparklines. En la versión conectada saldrán
 * de GET /camaras/{id}/lecturas; el contrato no las incluye en GET /camaras.
 */
export const seriesCamaras: Record<number, number[]> = {
  1: [
    1.2, 1.3, 1.25, 1.4, 1.35, 1.5, 1.45, 1.6, 1.7, 1.65, 1.8, 1.9, 1.85, 2.0,
    2.1, 2.05, 2.2, 2.3, 2.4, 2.5, 2.65, 2.8, 2.95, 3.1,
  ],
  2: [
    2.3, 2.2, 2.25, 2.35, 2.3, 2.2, 2.15, 2.25, 2.3, 2.35, 2.4, 2.3, 2.25, 2.2,
    2.3, 2.35, 2.4, 2.45, 2.4, 2.35, 2.3, 2.25, 2.35, 2.4,
  ],
  3: [
    3.1, 3.0, 3.05, 3.15, 3.1, 3.0, 2.95, 3.05, 3.1, 3.2, 3.15, 3.05, 3.0, 3.1,
    3.2, 3.25, 3.2, 3.1, 3.05, 3.15, 3.2, 3.25, 3.2, 3.2,
  ],
  4: [
    6.0, 5.9, 6.0, 6.1, 6.05, 5.95, 5.9, 6.0, 6.1, 6.15, 6.1, 6.0, 5.95, 6.0,
    6.05, 6.1, 6.15, 6.2, 6.15, 6.1, 6.05, 6.0, 6.05, 6.1,
  ],
  5: [
    -19.2, -19.3, -19.4, -19.5, -19.4, -19.3, -19.2, -19.3, -19.4, -19.5, -19.6,
    -19.5, -19.4, -19.3, -19.2, -19.3, -19.4, -19.5, -19.4, -19.3, -19.4, -19.5,
    -19.6, -19.4,
  ],
}

/** Dos eventos para la demostración del SIEM (forma de `alertas_seguridad`). */
export const alertasSeguridad: AlertaSeguridad[] = [
  {
    id: 1,
    regla_id: '3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41',
    regla: 'Fuerza bruta de tokens',
    severidad: 'high',
    ts: '2026-11-12T16:42:00-06:00',
    ip_origen: '187.190.12.4',
    detalle: { intentos: 12, ventana: '5 min', ruta: '/api/telemetria' },
    accion: 'bloquear_ip',
  },
  {
    id: 2,
    regla_id: '7d1c4a2e-5f83-4b69-9e07-1a6b8c3d2f50',
    regla: 'Lecturas imposibles',
    severidad: 'medium',
    ts: '2026-11-12T16:33:00-06:00',
    ip_origen: null,
    detalle: { sensor: 'S-PES-01', cambio: '8.6 °C', ventana: '45 s' },
    accion: 'marcar_lecturas',
  },
]
