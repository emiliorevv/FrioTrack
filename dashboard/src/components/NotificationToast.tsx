import { useCallback, useEffect, useRef } from 'react'
import type { Notificacion, TipoNotificacion } from '../types'

/** Tiempo que el toast permanece visible antes de cerrarse solo. */
export const DURACION_NOTIFICACION_MS = 10_000

const TITULOS: Record<TipoNotificacion, string> = {
  alerta_temperatura: 'Alerta de temperatura',
  alerta_puerta: 'Alerta de puerta',
  merma: 'Producto en merma',
}

interface NotificationToastProps {
  notificacion: Notificacion
  onCerrar: () => void
  /** Solo para pruebas; por defecto 10 s. */
  duracionMs?: number
}

export function NotificationToast({
  notificacion,
  onCerrar,
  duracionMs = DURACION_NOTIFICACION_MS,
}: NotificationToastProps) {
  const restanteRef = useRef(duracionMs)
  const inicioRef = useRef<number | null>(null)
  const timerRef = useRef<number | null>(null)
  const pausasRef = useRef(0)

  const detener = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (inicioRef.current !== null) {
      const transcurrido = Date.now() - inicioRef.current
      restanteRef.current = Math.max(0, restanteRef.current - transcurrido)
      inicioRef.current = null
    }
  }, [])

  const reanudar = useCallback(() => {
    if (timerRef.current !== null) {
      return
    }
    inicioRef.current = Date.now()
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null
      inicioRef.current = null
      onCerrar()
    }, restanteRef.current)
  }, [onCerrar])

  useEffect(() => {
    reanudar()
    return detener
  }, [reanudar, detener])

  const pausar = useCallback(() => {
    pausasRef.current += 1
    if (pausasRef.current === 1) {
      detener()
    }
  }, [detener])

  const despausar = useCallback(() => {
    pausasRef.current = Math.max(0, pausasRef.current - 1)
    if (pausasRef.current === 0) {
      reanudar()
    }
  }, [reanudar])

  const esMerma = notificacion.tipo === 'merma'

  return (
    <div
      className={`toast toast--${esMerma ? 'merma' : 'alerta'}`}
      role="alert"
      aria-atomic="true"
      onMouseEnter={pausar}
      onMouseLeave={despausar}
      onFocusCapture={pausar}
      onBlurCapture={despausar}
    >
      <div className="toast__body">
        <p className="toast__eyebrow">Notificación simulada</p>
        <p className="toast__title">{TITULOS[notificacion.tipo]}</p>
        <p className="toast__message">{notificacion.mensaje}</p>
      </div>

      <button
        type="button"
        className="icon-button toast__close"
        onClick={onCerrar}
        aria-label="Cerrar notificación"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <path d="m6 6 12 12M18 6 6 18" />
        </svg>
      </button>
    </div>
  )
}
