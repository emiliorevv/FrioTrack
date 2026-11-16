import { useEffect, useId, useRef, type ReactNode } from 'react'

/**
 * Pila de diálogos abiertos: Escape solo cierra el más reciente. Así un
 * formulario o un token dentro de Configuración no cierran también el panel.
 */
const pila: number[] = []
let siguienteId = 0

interface DialogoProps {
  titulo: string
  onCerrar: () => void
  children: ReactNode
  /** Botones fijos al pie del diálogo. */
  acciones?: ReactNode
  /** Nombre accesible del botón de cerrar. */
  etiquetaCerrar?: string
  className?: string
}

export function Dialogo({
  titulo,
  onCerrar,
  children,
  acciones,
  etiquetaCerrar = 'Cerrar',
  className,
}: DialogoProps) {
  const tituloId = useId()
  const panelRef = useRef<HTMLElement>(null)
  const cerrarRef = useRef(onCerrar)

  useEffect(() => {
    cerrarRef.current = onCerrar
  }, [onCerrar])

  useEffect(() => {
    const id = (siguienteId += 1)
    pila.push(id)
    const previo =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null

    // Foco inicial dentro del panel: primer campo o control, sin saltar al
    // contenido que quedó detrás del fondo.
    const panel = panelRef.current
    panel?.focus()
    const primerCampo = panel?.querySelector<HTMLElement>(
      'input:not([type="hidden"]), select, textarea',
    )
    const primeraPestana = panel?.querySelector<HTMLElement>('[role="tab"]')
    const primerBoton = panel?.querySelector<HTMLElement>('button')
    ;(primerCampo ?? primeraPestana ?? primerBoton ?? panel)?.focus()

    function alTeclear(evento: KeyboardEvent) {
      if (evento.key !== 'Escape' || pila[pila.length - 1] !== id) {
        return
      }
      evento.stopPropagation()
      cerrarRef.current()
    }

    document.addEventListener('keydown', alTeclear)
    return () => {
      document.removeEventListener('keydown', alTeclear)
      const posicion = pila.indexOf(id)
      if (posicion >= 0) {
        pila.splice(posicion, 1)
      }
      if (previo?.isConnected) {
        previo.focus()
      }
    }
  }, [])

  return (
    <div
      className="dialogo-fondo"
      onMouseDown={(evento) => {
        if (evento.target === evento.currentTarget) {
          onCerrar()
        }
      }}
    >
      <section
        className={`dialogo${className ? ` ${className}` : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={tituloId}
        tabIndex={-1}
        ref={panelRef}
      >
        <header className="dialogo__cabecera">
          <h2 className="dialogo__titulo" id={tituloId}>
            {titulo}
          </h2>
          <button
            type="button"
            className="icon-button"
            onClick={onCerrar}
            aria-label={etiquetaCerrar}
          >
            <svg
              width="15"
              height="15"
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
        </header>

        <div className="dialogo__cuerpo">{children}</div>

        {acciones && <footer className="dialogo__acciones">{acciones}</footer>}
      </section>
    </div>
  )
}
