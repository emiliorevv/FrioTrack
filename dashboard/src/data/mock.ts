import type { AlertaSeguridad } from '../types'

/**
 * Dos eventos para la demostración del SIEM (forma de `alertas_seguridad`).
 * El resto del dashboard ya usa datos reales; este panel sigue con ejemplos
 * porque el detector todavía no está conectado.
 */
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
