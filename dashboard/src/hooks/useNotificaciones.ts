import { useCallback, useRef, useState } from 'react'
import { parsearJson } from '../lib/sse'
import { esObjeto } from '../lib/validacion'
import { useStreamEvent } from '../realtime/StreamProvider'
import { TIPOS_NOTIFICACION, type Notificacion } from '../types'

/** Tope de la cola: si llegan más, se descartan las más viejas. */
export const MAX_NOTIFICACIONES = 5

export interface NotificacionEnCola {
  /** Id local incremental; sirve como `key` aunque dos eventos compartan `ts`. */
  id: number
  datos: Notificacion
}

/**
 * Cola FIFO de notificaciones simuladas.
 *
 * El evento `notificacion` lo publica el backend en `GET /api/stream`; su
 * contrato vive en `docs/contrato-api.md` (PR #37, dependencia de este PR).
 * La conexión, la reconexión y el JWT son responsabilidad de `StreamProvider`.
 */
export function useNotificaciones() {
  const [cola, setCola] = useState<NotificacionEnCola[]>([])
  const siguienteId = useRef(0)

  useStreamEvent('notificacion', (evento) => {
    const notificacion = leerNotificacion(evento.data)
    if (!notificacion) {
      return
    }

    siguienteId.current += 1
    const enCola: NotificacionEnCola = {
      id: siguienteId.current,
      datos: notificacion,
    }
    setCola((actual) =>
      actual.length < MAX_NOTIFICACIONES
        ? [...actual, enCola]
        : // La cola está llena: se conserva el toast visible (índice 0) y se
          // descarta el pendiente más antiguo.
          [actual[0], ...actual.slice(2), enCola],
    )
  })

  const cerrar = useCallback(() => {
    setCola((actual) => actual.slice(1))
  }, [])

  return { notificacion: cola[0] ?? null, cerrar }
}

function leerNotificacion(texto: string): Notificacion | null {
  const datos = parsearJson(texto)
  return esNotificacion(datos) ? datos : null
}

function esNotificacion(valor: unknown): valor is Notificacion {
  if (!esObjeto(valor)) {
    return false
  }
  const { mensaje, camara_id: camaraId, ts, tipo } = valor
  return (
    typeof mensaje === 'string' &&
    typeof camaraId === 'number' &&
    typeof ts === 'string' &&
    typeof tipo === 'string' &&
    TIPOS_NOTIFICACION.some((conocido) => conocido === tipo)
  )
}
