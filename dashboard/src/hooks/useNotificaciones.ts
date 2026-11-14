import { useCallback, useEffect, useRef, useState } from 'react'
import type { Notificacion } from '../types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000/api'

/** Tiempo que el toast permanece visible antes de descartarse solo. */
export const DURACION_NOTIFICACION_MS = 10_000

/**
 * Escucha el evento `notificacion` de `GET /api/stream` y guarda la última.
 * El resto de eventos del stream (`kpis`, `lectura`, …) se ignoran.
 */
export function useNotificaciones() {
  const [notificacion, setNotificacion] = useState<Notificacion | null>(null)
  const timerRef = useRef<number | null>(null)

  const limpiarTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const cerrar = useCallback(() => {
    limpiarTimer()
    setNotificacion(null)
  }, [limpiarTimer])

  useEffect(() => {
    // En SSR y en jsdom no hay EventSource: la vista sigue funcionando sin SSE.
    if (typeof EventSource === 'undefined') {
      return
    }

    const fuente = new EventSource(`${API_URL}/stream`)

    const alRecibir = (evento: MessageEvent<string>) => {
      let datos: unknown
      try {
        datos = JSON.parse(evento.data)
      } catch {
        return
      }
      if (!esNotificacion(datos)) {
        return
      }

      limpiarTimer()
      setNotificacion(datos)
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null
        setNotificacion(null)
      }, DURACION_NOTIFICACION_MS)
    }

    fuente.addEventListener('notificacion', alRecibir)

    return () => {
      // En `onerror` no se cierra: EventSource reintenta por su cuenta.
      fuente.removeEventListener('notificacion', alRecibir)
      fuente.close()
      limpiarTimer()
    }
  }, [limpiarTimer])

  return { notificacion, cerrar }
}

function esNotificacion(valor: unknown): valor is Notificacion {
  if (typeof valor !== 'object' || valor === null) {
    return false
  }
  const datos = valor as Record<string, unknown>
  return (
    typeof datos.mensaje === 'string' &&
    typeof datos.tipo === 'string' &&
    typeof datos.camara_id === 'number'
  )
}
