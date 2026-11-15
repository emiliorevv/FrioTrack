import type { AlertaSeguridad, SeveridadSeguridad } from '../types'
import {
  datosDeAlerta,
  etiquetaAccionDeAlerta,
  explicacionDeAlerta,
} from '../lib/siem'
import { TiempoRelativo } from './TiempoRelativo'

type TonoSeguridad = 'danger' | 'warn' | 'neutral'

const ETIQUETA_SEVERIDAD: Record<SeveridadSeguridad, string> = {
  low: 'Baja',
  medium: 'Media',
  high: 'Alta',
  critical: 'Crítica',
}

const TONO_SEVERIDAD: Record<SeveridadSeguridad, TonoSeguridad> = {
  low: 'neutral',
  medium: 'neutral',
  high: 'warn',
  critical: 'danger',
}

function etiquetaSeveridad(valor: string): string {
  return (ETIQUETA_SEVERIDAD as Record<string, string>)[valor] ?? 'Desconocida'
}

function tonoSeveridad(valor: string): TonoSeguridad {
  return (TONO_SEVERIDAD as Record<string, TonoSeguridad>)[valor] ?? 'neutral'
}

interface SecurityPanelProps {
  alertas: AlertaSeguridad[]
  /** `false` mientras no termina la primera carga. */
  cargado: boolean
  /** Fallo del carril de alertas; puede convivir con alertas previas. */
  error: string | null
}

export function SecurityPanel({ alertas, cargado, error }: SecurityPanelProps) {
  const mensajeVacio = error
    ? 'No se pudieron cargar las alertas del detector.'
    : cargado
      ? 'Sin alertas del detector.'
      : 'Cargando alertas del detector…'

  return (
    <section className="security" aria-labelledby="seguridad-title">
      <div className="section-heading">
        <div>
          <h2 id="seguridad-title">Seguridad</h2>
          <p>Reglas SIEM sobre los accesos a la API.</p>
        </div>
        <span className="tag">SIEM</span>
      </div>

      {error && alertas.length > 0 && (
        <p className="security__aviso">
          No se pudieron actualizar las alertas; mostrando las últimas
          conocidas.
        </p>
      )}

      {alertas.length === 0 ? (
        <p className="security__empty">{mensajeVacio}</p>
      ) : (
        <ul className="security__list">
          {alertas.map((alerta) => {
            const tono = tonoSeveridad(alerta.severidad)

            return (
              <li className="security__item" key={alerta.id}>
                <span
                  className={`security__dot security__dot--${tono}`}
                  aria-hidden="true"
                />
                <div className="security__body">
                  <p className="security__title">
                    {alerta.regla}
                    <span className={`tag tag--${tono}`}>
                      {etiquetaSeveridad(alerta.severidad)}
                    </span>
                  </p>
                  <p className="security__detail">
                    {alerta.ip_origen ?? 'Origen desconocido'} ·{' '}
                    {etiquetaAccionDeAlerta(alerta)}
                  </p>

                  <details className="security__details">
                    <summary>¿Qué pasó?</summary>
                    <div className="security__explicacion">
                      <p>{explicacionDeAlerta(alerta)}</p>
                      <dl className="security__datos">
                        {datosDeAlerta(alerta).map((dato) => (
                          <div key={dato.etiqueta}>
                            <dt>{dato.etiqueta}</dt>
                            <dd>{dato.valor}</dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  </details>
                </div>
                <TiempoRelativo className="security__time" ts={alerta.ts} />
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
