import type { Notificacion, TipoNotificacion } from '../types'

const TITULOS: Record<TipoNotificacion, string> = {
  alerta_temperatura: 'Alerta de temperatura',
  alerta_puerta: 'Alerta de puerta',
  merma: 'Producto en merma',
}

interface NotificationToastProps {
  notificacion: Notificacion
  onCerrar: () => void
}

export function NotificationToast({
  notificacion,
  onCerrar,
}: NotificationToastProps) {
  const esMerma = notificacion.tipo === 'merma'

  return (
    <div
      className={`toast toast--${esMerma ? 'merma' : 'alerta'}`}
      role="status"
      aria-live="polite"
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
