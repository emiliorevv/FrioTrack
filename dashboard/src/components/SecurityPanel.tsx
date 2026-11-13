import type {
  AccionSeguridad,
  AlertaSeguridad,
  SeveridadSeguridad,
} from '../types'
import { formatearHace } from '../lib/format'

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

const ETIQUETA_ACCION: Record<AccionSeguridad, string> = {
  bloquear_ip: 'IP bloqueada',
  revocar_token: 'Token revocado',
  marcar_lecturas: 'Lecturas marcadas',
}

function formatearValor(valor: unknown): string {
  if (Array.isArray(valor)) {
    return valor.map((item) => String(item)).join(', ')
  }
  if (valor !== null && typeof valor === 'object') {
    return JSON.stringify(valor)
  }
  return String(valor)
}

/** Vuelve legible el JSON de `detalle` sin inventar campos que no vengan ahí. */
function resumirDetalle(detalle: Record<string, unknown>): string {
  const partes = Object.entries(detalle).map(
    ([clave, valor]) =>
      `${clave.replaceAll('_', ' ')}: ${formatearValor(valor)}`,
  )
  return partes.length > 0 ? partes.join(' · ') : 'Sin detalle'
}

interface SecurityPanelProps {
  alertas: AlertaSeguridad[]
  ahora: Date
}

export function SecurityPanel({ alertas, ahora }: SecurityPanelProps) {
  return (
    <section className="security" aria-labelledby="seguridad-title">
      <div className="section-heading">
        <div>
          <h2 id="seguridad-title">Seguridad</h2>
          <p>Reglas SIEM sobre los accesos a la API.</p>
        </div>
        <span className="tag">SIEM</span>
      </div>

      <ul className="security__list">
        {alertas.map((alerta) => {
          const tono = TONO_SEVERIDAD[alerta.severidad]

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
                    {ETIQUETA_SEVERIDAD[alerta.severidad]}
                  </span>
                </p>
                <p className="security__detail">
                  {alerta.ip_origen && `${alerta.ip_origen} · `}
                  {resumirDetalle(alerta.detalle)} ·{' '}
                  {ETIQUETA_ACCION[alerta.accion]}
                </p>
              </div>
              <time className="security__time" dateTime={alerta.ts}>
                {formatearHace(alerta.ts, ahora)}
              </time>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
