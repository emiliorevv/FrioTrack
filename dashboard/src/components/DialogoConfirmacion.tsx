import { Dialogo } from './Dialogo'

interface DialogoConfirmacionProps {
  titulo: string
  mensaje: string
  etiquetaConfirmar: string
  /** Texto del botón mientras la petición está en vuelo. */
  etiquetaOcupado?: string
  /** Usa el estilo de acción destructiva. */
  peligro?: boolean
  error: string | null
  ocupado: boolean
  cerrable?: boolean
  onCancelar: () => void
  onConfirmar: () => void
}

/**
 * Confirmación compartida por Configuración e Inventario.
 *
 * `Dialogo` se encarga del focus trap, Escape, click en el fondo y de bloquear
 * el cierre cuando `cerrable` es falso.
 */
export function DialogoConfirmacion({
  titulo,
  mensaje,
  etiquetaConfirmar,
  etiquetaOcupado = 'Procesando…',
  peligro = false,
  error,
  ocupado,
  cerrable = true,
  onCancelar,
  onConfirmar,
}: DialogoConfirmacionProps) {
  return (
    <Dialogo
      titulo={titulo}
      onCerrar={onCancelar}
      etiquetaCerrar="Cancelar"
      cerrable={cerrable}
      acciones={
        <>
          <button
            type="button"
            className="boton boton--secundario"
            onClick={onCancelar}
            disabled={ocupado}
          >
            Cancelar
          </button>
          <button
            type="button"
            className={`boton ${peligro ? 'boton--peligro' : 'boton--primario'}`}
            onClick={onConfirmar}
            aria-busy={ocupado}
            disabled={ocupado}
          >
            {ocupado ? etiquetaOcupado : etiquetaConfirmar}
          </button>
        </>
      }
    >
      <p className="config__nota">{mensaje}</p>
      {error && (
        <p className="config-alerta" role="alert">
          {error}
        </p>
      )}
    </Dialogo>
  )
}
