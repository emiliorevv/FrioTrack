import { useEffect, useId, useRef, type ReactNode } from 'react'

/**
 * Pila de diálogos abiertos: Escape solo cierra el más reciente. Así un
 * formulario o un token dentro de Configuración no cierran también el panel.
 */
const pila: number[] = []
let siguienteId = 0

const SELECTOR_FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function focusablesVisibles(panel: HTMLElement): HTMLElement[] {
  return Array.from(
    panel.querySelectorAll<HTMLElement>(SELECTOR_FOCUSABLE),
  ).filter((elemento) => elemento.closest('[hidden]') === null)
}

interface DialogoProps {
  titulo: string
  onCerrar: () => void
  children: ReactNode
  /** Botones fijos al pie del diálogo. */
  acciones?: ReactNode
  /** Nombre accesible del botón de cerrar. */
  etiquetaCerrar?: string
  className?: string
  /**
   * Falso mientras una petición está en vuelo: X, Escape y el fondo dejan de
   * cerrar el diálogo superior.
   */
  cerrable?: boolean
}

export function Dialogo({
  titulo,
  onCerrar,
  children,
  acciones,
  etiquetaCerrar = 'Cerrar',
  className,
  cerrable = true,
}: DialogoProps) {
  const tituloId = useId()
  const panelRef = useRef<HTMLElement>(null)
  const cerrarRef = useRef(onCerrar)
  const cerrableRef = useRef(cerrable)

  useEffect(() => {
    cerrarRef.current = onCerrar
  }, [onCerrar])

  useEffect(() => {
    cerrableRef.current = cerrable
  }, [cerrable])

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
      'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])',
    )
    const primeraPestana = panel?.querySelector<HTMLElement>('[role="tab"]')
    const primerBoton = panel?.querySelector<HTMLElement>(
      'button:not([disabled])',
    )
    ;(primerCampo ?? primeraPestana ?? primerBoton ?? panel)?.focus()

    function alTeclear(evento: KeyboardEvent) {
      if (pila[pila.length - 1] !== id) {
        return
      }

      if (evento.key === 'Escape') {
        if (!cerrableRef.current) {
          return
        }
        evento.stopPropagation()
        cerrarRef.current()
        return
      }

      if (evento.key !== 'Tab' || !panel) {
        return
      }

      // Trap de foco: Tab y Shift+Tab se quedan en el diálogo superior.
      const focusables = focusablesVisibles(panel)
      if (focusables.length === 0) {
        evento.preventDefault()
        panel.focus()
        return
      }

      const primero = focusables[0]
      const ultimo = focusables[focusables.length - 1]
      const activo = document.activeElement

      if (evento.shiftKey) {
        if (activo === primero || activo === panel || !panel.contains(activo)) {
          evento.preventDefault()
          ultimo.focus()
        }
        return
      }

      if (activo === ultimo || activo === panel || !panel.contains(activo)) {
        evento.preventDefault()
        primero.focus()
      }
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
        if (evento.target === evento.currentTarget && cerrableRef.current) {
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
            disabled={!cerrable}
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
