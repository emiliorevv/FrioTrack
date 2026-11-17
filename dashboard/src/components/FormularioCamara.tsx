import { useId, useState, type FormEvent } from 'react'
import { mensajeDeError } from '../lib/erroresApi'
import { aNumero } from '../lib/validacion'
import type { Camara, CamaraCreacion } from '../types'
import { Campo } from './Campo'

interface FormularioCamaraProps {
  /** Cámara a editar; ausente para un alta. */
  camara?: Camara
  onGuardar: (datos: CamaraCreacion) => Promise<void>
  onCancelar: () => void
}

interface ErroresCampos {
  nombre?: string
  rango_min_c?: string
  rango_max_c?: string
  min_para_riesgo?: string
  min_para_merma?: string
}

function tieneUnDecimal(valor: number): boolean {
  return Math.abs(valor * 10 - Math.round(valor * 10)) < 1e-9
}

export function FormularioCamara({
  camara,
  onGuardar,
  onCancelar,
}: FormularioCamaraProps) {
  const baseId = useId()
  const [nombre, setNombre] = useState(camara?.nombre ?? '')
  const [rangoMin, setRangoMin] = useState(
    camara ? String(camara.rango_min_c) : '',
  )
  const [rangoMax, setRangoMax] = useState(
    camara ? String(camara.rango_max_c) : '',
  )
  const [riesgo, setRiesgo] = useState(
    camara ? String(camara.min_para_riesgo) : '',
  )
  const [merma, setMerma] = useState(
    camara ? String(camara.min_para_merma) : '',
  )
  const [errores, setErrores] = useState<ErroresCampos>({})
  const [errorServidor, setErrorServidor] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  function validar(): { datos: CamaraCreacion; errores: ErroresCampos } {
    const siguientes: ErroresCampos = {}
    const nombreLimpio = nombre.trim()
    if (nombreLimpio.length < 2 || nombreLimpio.length > 120) {
      siguientes.nombre = 'Escribe un nombre de 2 a 120 caracteres.'
    }

    const minimo = aNumero(rangoMin)
    if (
      minimo === null ||
      minimo < -50 ||
      minimo > 50 ||
      !tieneUnDecimal(minimo)
    ) {
      siguientes.rango_min_c =
        'El mínimo debe ser un número entre -50 y 50 °C, con un decimal.'
    }

    const maximo = aNumero(rangoMax)
    if (
      maximo === null ||
      maximo < -50 ||
      maximo > 50 ||
      !tieneUnDecimal(maximo)
    ) {
      siguientes.rango_max_c =
        'El máximo debe ser un número entre -50 y 50 °C, con un decimal.'
    }

    if (
      minimo !== null &&
      maximo !== null &&
      !siguientes.rango_min_c &&
      !siguientes.rango_max_c &&
      minimo >= maximo
    ) {
      siguientes.rango_min_c = 'El mínimo debe ser menor que el máximo.'
    }

    const minutosRiesgo = aNumero(riesgo)
    if (
      minutosRiesgo === null ||
      !Number.isInteger(minutosRiesgo) ||
      minutosRiesgo < 1
    ) {
      siguientes.min_para_riesgo =
        'Escribe un número entero de minutos, mínimo 1.'
    }

    const minutosMerma = aNumero(merma)
    if (
      minutosMerma === null ||
      !Number.isInteger(minutosMerma) ||
      minutosMerma < 1
    ) {
      siguientes.min_para_merma =
        'Escribe un número entero de minutos, mínimo 1.'
    } else if (
      minutosRiesgo !== null &&
      !siguientes.min_para_riesgo &&
      minutosMerma <= minutosRiesgo
    ) {
      siguientes.min_para_merma =
        'La merma debe ocurrir después del riesgo (más minutos).'
    }

    return {
      errores: siguientes,
      datos: {
        nombre: nombreLimpio,
        rango_min_c: minimo ?? 0,
        rango_max_c: maximo ?? 0,
        min_para_riesgo: minutosRiesgo ?? 0,
        min_para_merma: minutosMerma ?? 0,
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

    setGuardando(true)
    setErrorServidor(null)
    try {
      await onGuardar(resultado.datos)
    } catch (error) {
      setErrorServidor(mensajeDeError(error))
      setGuardando(false)
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
        <label className="campo__label" htmlFor={id('nombre')}>
          Nombre de la cámara
        </label>
        <input
          id={id('nombre')}
          className="campo__input"
          type="text"
          value={nombre}
          onChange={(evento) => setNombre(evento.target.value)}
          maxLength={120}
          required
          autoFocus
          aria-invalid={Boolean(errores.nombre)}
          aria-describedby={descrito('nombre')}
        />
        {errores.nombre ? (
          <p className="campo__error" id={id('nombre-error')} role="alert">
            {errores.nombre}
          </p>
        ) : (
          <p className="campo__ayuda" id={id('nombre-ayuda')}>
            Por ejemplo: “Cámara de pescados” o “Congelador”.
          </p>
        )}
      </div>

      <div className="form-grid">
        <Campo
          id={id('rango_min_c')}
          etiqueta="Rango mínimo (°C)"
          error={errores.rango_min_c}
          ayuda="Entre -50 y 50, con un decimal."
        >
          <input
            id={id('rango_min_c')}
            className="campo__input"
            type="number"
            inputMode="decimal"
            step="0.1"
            min="-50"
            max="50"
            value={rangoMin}
            onChange={(evento) => setRangoMin(evento.target.value)}
            required
            aria-invalid={Boolean(errores.rango_min_c)}
            aria-describedby={descrito('rango_min_c')}
          />
        </Campo>

        <Campo
          id={id('rango_max_c')}
          etiqueta="Rango máximo (°C)"
          error={errores.rango_max_c}
          ayuda="Debe ser mayor que el mínimo."
        >
          <input
            id={id('rango_max_c')}
            className="campo__input"
            type="number"
            inputMode="decimal"
            step="0.1"
            min="-50"
            max="50"
            value={rangoMax}
            onChange={(evento) => setRangoMax(evento.target.value)}
            required
            aria-invalid={Boolean(errores.rango_max_c)}
            aria-describedby={descrito('rango_max_c')}
          />
        </Campo>
      </div>

      <div className="form-grid">
        <Campo
          id={id('min_para_riesgo')}
          etiqueta="Minutos para riesgo"
          error={errores.min_para_riesgo}
          ayuda="Desde cuántos minutos fuera de rango hay riesgo."
        >
          <input
            id={id('min_para_riesgo')}
            className="campo__input"
            type="number"
            inputMode="numeric"
            step="1"
            min="1"
            value={riesgo}
            onChange={(evento) => setRiesgo(evento.target.value)}
            required
            aria-invalid={Boolean(errores.min_para_riesgo)}
            aria-describedby={descrito('min_para_riesgo')}
          />
        </Campo>

        <Campo
          id={id('min_para_merma')}
          etiqueta="Minutos para merma"
          error={errores.min_para_merma}
          ayuda="Debe ser mayor que los minutos de riesgo."
        >
          <input
            id={id('min_para_merma')}
            className="campo__input"
            type="number"
            inputMode="numeric"
            step="1"
            min="1"
            value={merma}
            onChange={(evento) => setMerma(evento.target.value)}
            required
            aria-invalid={Boolean(errores.min_para_merma)}
            aria-describedby={descrito('min_para_merma')}
          />
        </Campo>
      </div>

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
          {guardando ? 'Guardando…' : 'Guardar cámara'}
        </button>
      </div>
    </form>
  )
}
