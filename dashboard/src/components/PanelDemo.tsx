import { useEffect, useRef, useState } from 'react'
import {
  ErrorApi,
  recuperarDemo,
  simularAtaque,
  simularFalla,
  simularPuerta,
} from '../api/client'
import { Dialogo } from './Dialogo'

type AccionDemo = 'falla' | 'puerta' | 'ataque' | 'recuperar'

interface AccionPanel {
  id: AccionDemo
  etiqueta: string
  descripcion: string
  ejecutar: () => Promise<void>
  exito: string
  /** Refrescos posteriores al 202; el backend aplica el cambio en background. */
  refrescosMs: number[]
  etiquetaOcupado?: string
}

const ACCIONES: AccionPanel[] = [
  {
    id: 'falla',
    etiqueta: 'Simular falla de compresor',
    descripcion: 'Una cámara demo saldrá de su rango de temperatura.',
    ejecutar: simularFalla,
    exito: 'Simulación iniciada; observa las cámaras.',
    refrescosMs: [2_000, 30_000],
  },
  {
    id: 'puerta',
    etiqueta: 'Simular puerta abierta',
    descripcion: 'Una cámara demo quedará con la puerta abierta unos minutos.',
    ejecutar: simularPuerta,
    exito: 'Simulación iniciada; observa la alerta de puerta.',
    refrescosMs: [2_000, 30_000],
  },
  {
    id: 'ataque',
    etiqueta: 'Simular ataque SIEM',
    descripcion:
      'Se generará una alerta de seguridad simulada en el panel de Seguridad.',
    ejecutar: simularAtaque,
    exito: 'Ataque simulado; revisa el panel de Seguridad.',
    refrescosMs: [500],
  },
  {
    id: 'recuperar',
    etiqueta: 'Recuperar cámaras',
    descripcion:
      'Limpia la simulación y devuelve las cámaras demo a su estado normal.',
    ejecutar: recuperarDemo,
    exito: 'Cámaras recuperadas; el dashboard se actualizará.',
    refrescosMs: [2_000],
    etiquetaOcupado: 'Recuperando…',
  },
]

function mensajeDemo(fallo: unknown): string {
  if (fallo instanceof ErrorApi) {
    if (fallo.status === 404) {
      return 'La simulación no está disponible en este entorno.'
    }
    if (fallo.status === 403) {
      return 'Tu rol no permite usar la simulación.'
    }
    if (fallo.status === 409) {
      return (
        fallo.detalle ??
        'Ya hay una simulación en curso. Espera o recupera las cámaras.'
      )
    }
    return fallo.detalle ?? fallo.message
  }
  if (fallo instanceof Error) {
    return fallo.message
  }
  return 'No se pudo completar la simulación.'
}

interface PanelDemoProps {
  onCerrar: () => void
  /** Refresca cámaras/KPIs y el carril de seguridad del dashboard. */
  onCambio?: () => void
}

export function PanelDemo({ onCerrar, onCambio }: PanelDemoProps) {
  const [ocupado, setOcupado] = useState<AccionDemo | null>(null)
  const [mensaje, setMensaje] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timersRef = useRef<number[]>([])
  const onCambioRef = useRef(onCambio)

  useEffect(() => {
    onCambioRef.current = onCambio
  }, [onCambio])

  useEffect(
    () => () => {
      for (const timer of timersRef.current) {
        window.clearTimeout(timer)
      }
      timersRef.current = []
    },
    [],
  )

  function limpiarTimers() {
    for (const timer of timersRef.current) {
      window.clearTimeout(timer)
    }
    timersRef.current = []
  }

  function programarRefrescos(delays: number[]) {
    limpiarTimers()
    for (const delay of delays) {
      timersRef.current.push(
        window.setTimeout(() => onCambioRef.current?.(), delay),
      )
    }
  }

  async function ejecutar(accion: AccionPanel) {
    if (ocupado !== null) {
      return
    }
    setOcupado(accion.id)
    setMensaje(null)
    setError(null)
    try {
      await accion.ejecutar()
      setMensaje(accion.exito)
      programarRefrescos(accion.refrescosMs)
    } catch (fallo) {
      setError(mensajeDemo(fallo))
    } finally {
      setOcupado(null)
    }
  }

  return (
    <Dialogo
      titulo="Panel de demo"
      onCerrar={onCerrar}
      etiquetaCerrar="Cerrar panel de demo"
      className="panel-demo"
      cerrable={ocupado === null}
    >
      <p className="config__nota">
        Atajos para la exposición. Solo afectan al restaurante demo y el
        dashboard se refresca unos segundos después.
      </p>

      {mensaje && (
        <p className="panel-demo__mensaje" role="status">
          {mensaje}
        </p>
      )}
      {error && (
        <p className="config-alerta" role="alert">
          {error}
        </p>
      )}

      <ul className="panel-demo__acciones">
        {ACCIONES.map((accion) => {
          const enCurso = ocupado === accion.id
          return (
            <li className="panel-demo__accion" key={accion.id}>
              <div className="panel-demo__texto">
                <p className="panel-demo__titulo">{accion.etiqueta}</p>
                <p className="panel-demo__descripcion">{accion.descripcion}</p>
              </div>
              <button
                type="button"
                className={`boton ${
                  accion.id === 'recuperar'
                    ? 'boton--secundario'
                    : 'boton--primario'
                }`}
                onClick={() => void ejecutar(accion)}
                aria-busy={enCurso}
                disabled={ocupado !== null}
              >
                {enCurso
                  ? (accion.etiquetaOcupado ?? 'Simulando…')
                  : accion.etiqueta}
              </button>
            </li>
          )
        })}
      </ul>
    </Dialogo>
  )
}
