import { useReloj } from '../hooks/useReloj'

interface HeaderProps {
  /** Última actualización con datos; `null` = todavía no hay datos. */
  actualizadoEn: Date | null
  /**
   * `escala_tiempo` de GET /api/health. En 1 (tiempo real) no se muestra la
   * etiqueta de demo; si `/health` falla, no hay etiqueta.
   */
  escalaTiempo?: number
  /** Iniciales del usuario logueado; hoy no hay auth y el default es JC. */
  iniciales?: string
}

export function Header({
  actualizadoEn,
  escalaTiempo,
  iniciales = 'JC',
}: HeaderProps) {
  const mostrarModoDemo = escalaTiempo !== undefined && escalaTiempo !== 1

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
          <span
            className="avatar"
            role="img"
            aria-label={`Sesión de ${iniciales}, jefe de cocina`}
          >
            {iniciales}
          </span>
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
