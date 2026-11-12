interface HeaderProps {
  actualizadoHaceSegundos: number
}

export function Header({ actualizadoHaceSegundos }: HeaderProps) {
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
          <span className="demo-pill">MODO DEMO ×30</span>
          <span className="updated">
            <span className="updated__dot" aria-hidden="true" />
            Actualizado hace {actualizadoHaceSegundos} s
          </span>
          <span
            className="avatar"
            role="img"
            aria-label="Sesión de JC, jefe de cocina"
          >
            JC
          </span>
        </div>
      </div>
    </header>
  )
}
