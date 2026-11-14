/** Eventos que publica el backend en `GET /api/stream`. */
export const EVENTOS_STREAM = [
  'notificacion',
  'kpis',
  'lectura',
  'alerta_abierta',
  'alerta_cerrada',
  'lote_actualizado',
] as const

export type EventoStream = (typeof EVENTOS_STREAM)[number]

/** Base y tope del backoff de reconexión del stream. */
export const RECONEXION_BASE_MS = 5_000
export const RECONEXION_MAX_MS = 30_000

/**
 * Backoff exponencial con jitter de ±25 % y tope de 30 s: 5, 10, 20, 30, 30…
 * El jitter evita que todas las pestañas reintenten en lockstep.
 */
export function retrasoReconexion(
  intento: number,
  aleatorio = Math.random(),
): number {
  const base = Math.min(RECONEXION_BASE_MS * 2 ** intento, RECONEXION_MAX_MS)
  return Math.round(base * (0.75 + aleatorio * 0.5))
}

/** Arma la URL del stream y añade `?token=` solo cuando hay JWT. */
export function construirUrlStream(base: string, token?: string): string {
  const url = `${base}/stream`
  return token ? `${url}?token=${encodeURIComponent(token)}` : url
}
