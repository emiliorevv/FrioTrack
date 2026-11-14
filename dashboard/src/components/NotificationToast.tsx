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
  const raizRef = useRef<HTMLDivElement>(null)
  const restanteRef = useRef(duracionMs)
  const inicioRef = useRef<number | null>(null)
  const timerRef = useRef<number | null>(null)
  const punteroEncimaRef = useRef(false)
  const focoDentroRef = useRef(false)

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

  /** Pausa si el puntero está encima o el foco sigue dentro; si no, reanuda. */
  const actualizarPausa = useCallback(() => {
    if (punteroEncimaRef.current || focoDentroRef.current) {
      detener()
    } else {
      reanudar()
    }
  }, [detener, reanudar])

  useEffect(() => {
    // El toast puede montarse debajo de un puntero quieto o con el foco ya
    // dentro (p. ej. el toast anterior): en ese caso no arranca el timer.
    const raiz = raizRef.current
    punteroEncimaRef.current = raiz?.matches(':hover') ?? false
    focoDentroRef.current = raiz?.contains(document.activeElement) ?? false
    actualizarPausa()

    return detener
  }, [actualizarPausa, detener])

  const alEntrarPuntero = useCallback(() => {
    punteroEncimaRef.current = true
    actualizarPausa()
  }, [actualizarPausa])

  const alSalirPuntero = useCallback(() => {
    punteroEncimaRef.current = false
    actualizarPausa()
  }, [actualizarPausa])

  const alEntrarFoco = useCallback(() => {
    focoDentroRef.current = true
    actualizarPausa()
  }, [actualizarPausa])

  const alSalirFoco = useCallback(() => {
    focoDentroRef.current = false
    actualizarPausa()
  }, [actualizarPausa])

  const cerrar = useCallback(() => {
    onCerrar()
    // Si se cerró por teclado, el botón desaparece y el foco cae a <body>.
    requestAnimationFrame(() => {
      document.getElementById('contenido')?.focus({ preventScroll: true })
    })
  }, [onCerrar])

  const esMerma = notificacion.tipo === 'merma'

  return (
    <div
      ref={raizRef}
      className={`toast toast--${esMerma ? 'merma' : 'alerta'}`}
      role="alert"
      aria-atomic="true"
      onMouseEnter={alEntrarPuntero}
      onMouseLeave={alSalirPuntero}
      onFocusCapture={alEntrarFoco}
      onBlurCapture={alSalirFoco}
    >
      <div className="toast__body">
        <p className="toast__eyebrow">Notificación simulada</p>
        <p className="toast__title">{TITULOS[notificacion.tipo]}</p>
        <p className="toast__message">{notificacion.mensaje}</p>
      </div>

      <button
        type="button"
        className="icon-button toast__close"
        onClick={cerrar}
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
