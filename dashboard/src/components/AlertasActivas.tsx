import { useMemo } from 'react'
import { formatearTemperatura } from '../lib/format'
import type { AlertaOperativa, Camara } from '../types'
import { TiempoRelativo } from './TiempoRelativo'

const ETIQUETA_TIPO: Record<string, string> = {
  temperatura: 'Temperatura',
  puerta: 'Puerta',
}

function etiquetaTipo(tipo: string): string {
  return ETIQUETA_TIPO[tipo] ?? 'Alerta'
}

interface AlertasActivasProps {
  alertas: AlertaOperativa[]
  camaras: Camara[]
  cargando: boolean
  error: string | null
  atendiendo: Record<number, boolean>
  onAtender: (id: number) => void
}

export function AlertasActivas({
  alertas,
  camaras,
  cargando,
  error,
  atendiendo,
  onAtender,
}: AlertasActivasProps) {
  const nombres = useMemo(
    () => new Map(camaras.map((camara) => [camara.id, camara.nombre])),
    [camaras],
  )

  return (
    <section
      className="section alertas-activas"
      aria-labelledby="alertas-activas-title"
    >
      <div className="section-heading">
        <div>
          <h2 id="alertas-activas-title">
            Alertas activas
            <span className="alertas-activas__count">{alertas.length}</span>
          </h2>
          <p>Requieren atención del turno.</p>
        </div>
      </div>

      <div
        className="alertas-activas__contenido"
        aria-live="polite"
        aria-busy={cargando}
      >
        {error && alertas.length === 0 && (
          <p className="alertas-activas__error" role="status">
            No se pudieron cargar las alertas activas.
          </p>
        )}

        {error && alertas.length > 0 && (
          <p className="alertas-activas__error" role="status">
            No se pudieron actualizar las alertas activas; mostrando las últimas
            conocidas.
          </p>
        )}

        {cargando && alertas.length === 0 ? (
          <p className="alertas-activas__empty">Cargando alertas…</p>
        ) : alertas.length === 0 ? (
          !error && (
            <p className="alertas-activas__empty">Sin alertas activas</p>
          )
        ) : (
          <ul className="alertas-activas__list">
            {alertas.map((alerta) => {
              const ocupada = atendiendo[alerta.id] === true
              const atendida = alerta.atendida_por !== null
              const nombre =
                nombres.get(alerta.camara_id) ?? `Cámara ${alerta.camara_id}`

              return (
                <li className="alerta-activa" key={alerta.id}>
                  <div className="alerta-activa__body">
                    <p className="alerta-activa__title">
                      {nombre}
                      <span className="tag">{etiquetaTipo(alerta.tipo)}</span>
                    </p>
                    <p className="alerta-activa__meta">
                      <TiempoRelativo ts={alerta.abierta_en} />
                      {alerta.temperatura_max_c !== null && (
                        <span>
                          {' '}
                          · Máx.{' '}
                          {formatearTemperatura(alerta.temperatura_max_c)} °C
                        </span>
                      )}
                    </p>
                  </div>

                  <button
                    type="button"
                    className="retry-button retry-button--sm alerta-activa__accion"
                    disabled={ocupada || atendida}
                    aria-busy={ocupada}
                    onClick={() => onAtender(alerta.id)}
                  >
                    {ocupada
                      ? 'Atendiendo…'
                      : atendida
                        ? 'Atendida'
                        : 'Atender'}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}
