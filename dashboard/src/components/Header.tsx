interface HeaderProps {
  actualizadoHaceSegundos: number
  /**
   * `escala_tiempo` de GET /api/health. En 1 (tiempo real) no se muestra la
   * etiqueta de demo; mientras no haya API, App pasa 30.
   */
  escalaTiempo?: number
  /** Iniciales del usuario logueado; hoy no hay auth y el default es JC. */
  iniciales?: string
}

export function Header({
  actualizadoHaceSegundos,
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
          <span className="updated">
            <span className="updated__dot" aria-hidden="true" />
            Actualizado hace {actualizadoHaceSegundos} s
          </span>
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
