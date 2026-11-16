import { etiquetaRol } from '../auth/roles'
import { useReloj } from '../hooks/useReloj'

interface HeaderProps {
  /** Última actualización con datos; `null` = todavía no hay datos. */
  actualizadoEn: Date | null
  /**
   * `escala_tiempo` de GET /api/health. En 1 (tiempo real) no se muestra la
   * etiqueta de demo; si `/health` falla, no hay etiqueta.
   */
  escalaTiempo?: number
  usuario: string
  rol: string
  onLogout: () => void
  /** Abre Configuración; solo se muestra para el rol dueño. */
  onAbrirConfiguracion?: () => void
}

function inicialesDe(usuario: string): string {
  const limpio = usuario.trim()
  return limpio ? limpio.slice(0, 2).toUpperCase() : 'US'
}

export function Header({
  actualizadoEn,
  escalaTiempo,
  usuario,
  rol,
  onLogout,
  onAbrirConfiguracion,
}: HeaderProps) {
  const mostrarModoDemo = escalaTiempo !== undefined && escalaTiempo !== 1
  const nombreRol = etiquetaRol(rol)

  return (
    <header className="site-header">
      <div className="site-header__inner">
        <div className="brand">
          <h1 className="brand__name">
            FríoTrack
            <span className="brand__dot" aria-hidden="true">
              .
            </span>
          </h1>
          <p className="brand__tagline">Cadena de frío · monitoreo continuo</p>
        </div>

        <div className="site-header__meta">
          {mostrarModoDemo && (
            <span className="demo-pill">MODO DEMO ×{escalaTiempo}</span>
          )}
          {actualizadoEn ? (
            <ActualizadoHace actualizadoEn={actualizadoEn} />
          ) : (
            <span className="updated">Sin datos</span>
          )}

          {rol === 'dueno' && onAbrirConfiguracion && (
            <button
              type="button"
              className="header-config"
              onClick={onAbrirConfiguracion}
              aria-label="Configuración"
              title="Configuración"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" />
              </svg>
              <span className="header-config__texto">Configuración</span>
            </button>
          )}

          <div className="session">
            <span
              className="avatar"
              role="img"
              aria-label={`Sesión de ${usuario}, ${nombreRol}`}
            >
              {inicialesDe(usuario)}
            </span>
            <span className="session__data">
              <span className="session__name">{usuario}</span>
              <span className="session__role">{nombreRol}</span>
            </span>
            <button
              type="button"
              className="session__logout"
              onClick={onLogout}
              title="Cerrar sesión"
            >
              Salir
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}

/** El reloj vive aquí: solo este texto se re-renderiza cada segundo. */
function ActualizadoHace({ actualizadoEn }: { actualizadoEn: Date }) {
  const ahora = useReloj()
  const segundos = Math.max(
    0,
    Math.floor((ahora.getTime() - actualizadoEn.getTime()) / 1000),
  )

  return (
    <span className="updated">
      <span className="updated__dot" aria-hidden="true" />
      Actualizado hace {segundos} s
    </span>
  )
}
