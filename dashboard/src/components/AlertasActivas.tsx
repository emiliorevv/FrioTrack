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
  /** Fallo del listado de alertas. */
  error: string | null
  /** Fallo de la última acción de atender, con el `detail` del backend. */
  errorAtender: string | null
  atendiendo: Record<number, boolean>
  /** Solo el jefe de cocina puede ejecutar la acción. */
  puedeAtender: boolean
  onAtender: (id: number) => void
  onLimpiarErrorAtender: () => void
}

export function AlertasActivas({
  alertas,
  camaras,
  cargando,
  error,
  errorAtender,
  atendiendo,
  puedeAtender,
  onAtender,
  onLimpiarErrorAtender,
}: AlertasActivasProps) {
  const nombres = useMemo(
    () => new Map(camaras.map((camara) => [camara.id, camara.nombre])),
    [camaras],
  )
  const pendientes = alertas.filter(
    (alerta) => alerta.atendida_por === null,
  ).length
  const textoPendientes =
    pendientes === 1
      ? '1 pendiente de atención'
      : `${pendientes} pendientes de atención`
  const textoEstado =
    cargando && alertas.length === 0
      ? 'Cargando alertas…'
      : `${alertas.length} ${
          alertas.length === 1 ? 'activa' : 'activas'
        }; ${textoPendientes}`

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
          <p>{textoPendientes}</p>
          {!puedeAtender && (
            <p className="alertas-activas__permiso" id="alertas-permiso">
              Solo jefe de cocina puede atender.
            </p>
          )}
        </div>
      </div>

      {/* Solo cambia con los conteos, nunca con el reloj de cada tarjeta. */}
      <p className="visually-hidden" role="status">
        {textoEstado}
      </p>

      <div className="alertas-activas__contenido" aria-busy={cargando}>
        {error && (
          <p className="alertas-activas__error" role="status">
            {alertas.length === 0
              ? 'No se pudieron cargar las alertas activas.'
              : 'No se pudieron actualizar las alertas activas; mostrando las últimas conocidas.'}
          </p>
        )}

        {errorAtender && (
          <div
            className="alertas-activas__error alertas-activas__error--accion"
            role="alert"
          >
            <p>{errorAtender}</p>
            <button
              type="button"
              className="alertas-activas__cerrar"
              onClick={onLimpiarErrorAtender}
            >
              Cerrar
            </button>
          </div>
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
                    disabled={ocupada || atendida || !puedeAtender}
                    aria-busy={ocupada}
                    aria-describedby={
                      puedeAtender ? undefined : 'alertas-permiso'
                    }
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
