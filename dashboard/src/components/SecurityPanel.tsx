import type {
  AccionSeguridad,
  AlertaSeguridad,
  SeveridadSeguridad,
} from '../types'
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

const ETIQUETA_ACCION: Record<AccionSeguridad, string> = {
  bloquear_ip: 'IP bloqueada',
  revocar_token: 'Token revocado',
  marcar_lecturas: 'Lecturas marcadas',
}

/**
 * El backend guarda strings libres. Los conocidos se etiquetan aquí; el
 * resto cae al fallback para no romper el render.
 */
function etiquetaSeveridad(valor: string): string {
  return (ETIQUETA_SEVERIDAD as Record<string, string>)[valor] ?? 'Desconocida'
}

function tonoSeveridad(valor: string): TonoSeguridad {
  return (TONO_SEVERIDAD as Record<string, TonoSeguridad>)[valor] ?? 'neutral'
}

function etiquetaAccion(valor: string): string {
  return (ETIQUETA_ACCION as Record<string, string>)[valor] ?? 'Sin acción'
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
                    {alerta.ip_origen && `${alerta.ip_origen} · `}
                    {resumirDetalle(alerta.detalle)} ·{' '}
                    {etiquetaAccion(alerta.accion)}
                  </p>
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
