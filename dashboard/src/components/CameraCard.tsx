import type { Camara, EstadoCamara } from '../types'
import {
  formatearHace,
  formatearMxn,
  formatearRango,
  formatearTemperatura,
} from '../lib/format'
import { Sparkline } from './Sparkline'

const ETIQUETA_ESTADO: Record<EstadoCamara, string> = {
  en_rango: 'En rango',
  alerta: 'Alerta',
  critica: 'Crítica',
}

interface CameraCardProps {
  camara: Camara
  serie: number[]
  ahora: Date
}

export function CameraCard({ camara, serie, ahora }: CameraCardProps) {
  const lectura = camara.ultima_lectura
  const tituloId = `camara-${camara.id}`
  const enRiesgo = camara.valor_en_riesgo_mxn > 0

  return (
    <article
      className={`camera-card camera-card--${camara.estado}`}
      aria-labelledby={tituloId}
    >
      <div className="camera-card__top">
        <span className={`status status--${camara.estado}`}>
          <span className="status__dot" aria-hidden="true" />
          {ETIQUETA_ESTADO[camara.estado]}
        </span>
        <span className="camera-card__age">
          {formatearHace(lectura.ts, ahora)}
        </span>
      </div>

      <h3 id={tituloId} className="camera-card__name">
        {camara.nombre}
      </h3>

      <p className="camera-card__temperature">
        <span className="camera-card__value">
          {formatearTemperatura(lectura.temperatura_c)}
        </span>
        <span className="camera-card__unit">°C</span>
      </p>

      <dl className="camera-card__meta">
        <div>
          <dt>Rango</dt>
          <dd>
            {formatearRango(camara.rango_min_c)}–
            {formatearRango(camara.rango_max_c)} °C
          </dd>
        </div>
        <div>
          <dt>Puerta</dt>
          <dd className={lectura.puerta_abierta ? 'is-warn' : undefined}>
            {lectura.puerta_abierta ? 'Abierta' : 'Cerrada'}
          </dd>
        </div>
        <div>
          <dt>En riesgo</dt>
          <dd className={enRiesgo ? 'is-warn' : undefined}>
            {formatearMxn(camara.valor_en_riesgo_mxn)}
          </dd>
        </div>
      </dl>

      <Sparkline
        serie={serie}
        rangoMin={camara.rango_min_c}
        rangoMax={camara.rango_max_c}
        estado={camara.estado}
        nombre={camara.nombre}
      />
    </article>
  )
}
