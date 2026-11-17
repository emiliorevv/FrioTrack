import { useId, useState, type FormEvent } from 'react'
import { mensajeDeError } from '../lib/erroresApi'
import { fechaVencida, formatearFecha } from '../lib/format'
import { aNumero } from '../lib/validacion'
import type { Camara, Lote, LoteCreacion, UnidadLote } from '../types'
import { Campo } from './Campo'

interface FormularioLoteProps {
  /** Lote a editar; ausente para un alta. */
  lote?: Lote
  camaras: Camara[]
  /** Estado de la petición; la única fuente de verdad es `Inventario`. */
  guardando: boolean
  onGuardar: (datos: LoteCreacion) => Promise<void>
  onCancelar: () => void
}

interface ErroresCampos {
  producto?: string
  camara_id?: string
  cantidad?: string
  unidad?: string
  costo_total_mxn?: string
  caducidad?: string
}

const UNIDADES: { valor: UnidadLote; etiqueta: string }[] = [
  { valor: 'kg', etiqueta: 'Kilogramos (kg)' },
  { valor: 'l', etiqueta: 'Litros (l)' },
  { valor: 'pz', etiqueta: 'Piezas (pz)' },
]

function hastaDosDecimales(valor: number): boolean {
  return Math.abs(valor * 100 - Math.round(valor * 100)) < 1e-7
}

function fechaValida(valor: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(valor)) {
    return false
  }
  const [anio, mes, dia] = valor.split('-').map(Number)
  const fecha = new Date(anio, mes - 1, dia)
  return (
    fecha.getFullYear() === anio &&
    fecha.getMonth() === mes - 1 &&
    fecha.getDate() === dia
  )
}

export function FormularioLote({
  lote,
  camaras,
  guardando,
  onGuardar,
  onCancelar,
}: FormularioLoteProps) {
  const baseId = useId()
  const [producto, setProducto] = useState(lote?.producto ?? '')
  const [camaraId, setCamaraId] = useState(lote ? String(lote.camara_id) : '')
  const [cantidad, setCantidad] = useState(lote ? String(lote.cantidad) : '')
  const [unidad, setUnidad] = useState<UnidadLote>(lote?.unidad ?? 'kg')
  const [costo, setCosto] = useState(lote ? String(lote.costo_total_mxn) : '')
  const [caducidad, setCaducidad] = useState(lote?.caducidad ?? '')
  const [errores, setErrores] = useState<ErroresCampos>({})
  const [errorServidor, setErrorServidor] = useState<string | null>(null)

  const camaraActual = lote
    ? (camaras.find((actual) => actual.id === lote.camara_id) ?? {
        id: lote.camara_id,
        nombre: `Cámara ${lote.camara_id}`,
      })
    : null
  const camarasDisponibles =
    camaraActual && !camaras.some((actual) => actual.id === camaraActual.id)
      ? [...camaras, camaraActual]
      : camaras

  const advertenciaCaducidad =
    Boolean(caducidad) && !errores.caducidad && fechaVencida(caducidad)

  function validar(): { datos: LoteCreacion; errores: ErroresCampos } {
    const siguientes: ErroresCampos = {}
    const productoLimpio = producto.trim()
    if (productoLimpio.length < 2 || productoLimpio.length > 120) {
      siguientes.producto = 'Escribe un producto de 2 a 120 caracteres.'
    }

    const camara = camarasDisponibles.find(
      (actual) => String(actual.id) === camaraId,
    )
    if (!camara) {
      siguientes.camara_id = 'Selecciona una cámara.'
    }

    const cantidadNumero = aNumero(cantidad)
    if (
      cantidadNumero === null ||
      cantidadNumero <= 0 ||
      cantidadNumero > 999999.99 ||
      !hastaDosDecimales(cantidadNumero)
    ) {
      siguientes.cantidad =
        'La cantidad debe ser mayor que 0, con hasta 2 decimales.'
    }

    const costoNumero = aNumero(costo)
    if (
      costoNumero === null ||
      costoNumero < 0 ||
      costoNumero > 99999999.99 ||
      !hastaDosDecimales(costoNumero)
    ) {
      siguientes.costo_total_mxn =
        'El costo debe ser 0 o más, con hasta 2 decimales.'
    }

    if (!fechaValida(caducidad)) {
      siguientes.caducidad = 'Escribe una fecha de caducidad válida.'
    }

    return {
      errores: siguientes,
      datos: {
        producto: productoLimpio,
        camara_id: camara?.id ?? 0,
        cantidad: cantidadNumero ?? 0,
        unidad,
        costo_total_mxn: costoNumero ?? 0,
        caducidad,
      },
    }
  }

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const resultado = validar()
    setErrores(resultado.errores)
    if (Object.keys(resultado.errores).length > 0) {
      return
    }

    setErrorServidor(null)
    try {
      await onGuardar(resultado.datos)
    } catch (error) {
      setErrorServidor(mensajeDeError(error, 'lote'))
    }
  }

  function id(campo: string) {
    return `${baseId}-${campo}`
  }

  function descrito(campo: keyof ErroresCampos) {
    return errores[campo] ? id(`${campo}-error`) : id(`${campo}-ayuda`)
  }

  return (
    <form
      className="config-form"
      noValidate
      onSubmit={(evento) => void enviar(evento)}
    >
      {errorServidor && (
        <p className="config-alerta" role="alert">
          {errorServidor}
        </p>
      )}

      <div className="campo">
        <label className="campo__label" htmlFor={id('producto')}>
          Producto
        </label>
        <input
          id={id('producto')}
          className="campo__input"
          type="text"
          value={producto}
          onChange={(evento) => setProducto(evento.target.value)}
          maxLength={120}
          required
          autoFocus
          aria-invalid={Boolean(errores.producto)}
          aria-describedby={descrito('producto')}
        />
        {errores.producto ? (
          <p className="campo__error" id={id('producto-error')} role="alert">
            {errores.producto}
          </p>
        ) : (
          <p className="campo__ayuda" id={id('producto-ayuda')}>
            Por ejemplo: “Salmón fresco” o “Leche entera”.
          </p>
        )}
      </div>

      <Campo
        id={id('camara_id')}
        etiqueta="Cámara"
        error={errores.camara_id}
        ayuda="Solo se listan las cámaras de tu restaurante."
      >
        <select
          id={id('camara_id')}
          className="campo__input"
          value={camaraId}
          onChange={(evento) => setCamaraId(evento.target.value)}
          required
          aria-invalid={Boolean(errores.camara_id)}
          aria-describedby={descrito('camara_id')}
        >
          <option value="">Selecciona una cámara</option>
          {camarasDisponibles.map((camara) => (
            <option key={camara.id} value={camara.id}>
              {camara.nombre}
            </option>
          ))}
        </select>
      </Campo>

      <div className="form-grid">
        <Campo
          id={id('cantidad')}
          etiqueta="Cantidad"
          error={errores.cantidad}
          ayuda="Mayor que 0, hasta 2 decimales."
        >
          <input
            id={id('cantidad')}
            className="campo__input"
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0.01"
            value={cantidad}
            onChange={(evento) => setCantidad(evento.target.value)}
            required
            aria-invalid={Boolean(errores.cantidad)}
            aria-describedby={descrito('cantidad')}
          />
        </Campo>

        <Campo
          id={id('unidad')}
          etiqueta="Unidad"
          error={errores.unidad}
          ayuda="Kilogramos, litros o piezas."
        >
          <select
            id={id('unidad')}
            className="campo__input"
            value={unidad}
            onChange={(evento) => setUnidad(evento.target.value as UnidadLote)}
            aria-describedby={descrito('unidad')}
          >
            {UNIDADES.map((opcion) => (
              <option key={opcion.valor} value={opcion.valor}>
                {opcion.etiqueta}
              </option>
            ))}
          </select>
        </Campo>
      </div>

      <div className="form-grid">
        <Campo
          id={id('costo_total_mxn')}
          etiqueta="Costo total (MXN)"
          error={errores.costo_total_mxn}
          ayuda="0 o más, hasta 2 decimales."
        >
          <input
            id={id('costo_total_mxn')}
            className="campo__input"
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0"
            value={costo}
            onChange={(evento) => setCosto(evento.target.value)}
            required
            aria-invalid={Boolean(errores.costo_total_mxn)}
            aria-describedby={descrito('costo_total_mxn')}
          />
        </Campo>

        <Campo
          id={id('caducidad')}
          etiqueta="Caducidad"
          error={errores.caducidad}
          ayuda="Puede ser una fecha pasada; se guardará igual."
        >
          <input
            id={id('caducidad')}
            className="campo__input"
            type="date"
            value={caducidad}
            onChange={(evento) => setCaducidad(evento.target.value)}
            required
            aria-invalid={Boolean(errores.caducidad)}
            aria-describedby={descrito('caducidad')}
          />
        </Campo>
      </div>

      {advertenciaCaducidad && (
        <p className="campo__aviso" role="status">
          Este lote está vencido ({formatearFecha(caducidad)}), pero puedes
          guardarlo para conservar el registro.
        </p>
      )}

      <div className="config-form__acciones">
        <button
          type="button"
          className="boton boton--secundario"
          onClick={onCancelar}
          disabled={guardando}
        >
          Cancelar
        </button>
        <button
          type="submit"
          className="boton boton--primario"
          aria-busy={guardando}
          disabled={guardando}
        >
          {guardando ? 'Guardando…' : 'Guardar lote'}
        </button>
      </div>
    </form>
  )
}
