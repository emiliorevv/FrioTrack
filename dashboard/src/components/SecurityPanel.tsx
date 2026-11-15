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

/** IDs de `security/siem/*.yml`; el detector los manda tal cual. */
const ID_FUERZA_BRUTA = '3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41'
const ID_TOKEN_DESCONOCIDO = 'e26aa409-804c-47fb-b852-1786ddaa172d'
const ID_LECTURAS_IMPOSIBLES = '26f277c2-6d7a-4ff2-b44c-452f2788f824'

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

function explicacionDeAlerta(alerta: AlertaSeguridad): string {
  switch (alerta.regla_id) {
    case ID_FUERZA_BRUTA:
      return 'Detectamos varios intentos fallidos de inicio de sesión desde la misma dirección. Para proteger el sistema, bloqueamos esa IP durante 60 minutos.'
    case ID_TOKEN_DESCONOCIDO:
      return 'Un sensor válido se usó desde una red que no es la del restaurante. Revocamos su token para evitar lecturas falsas.'
    case ID_LECTURAS_IMPOSIBLES:
      return 'Una cámara reportó un cambio de temperatura demasiado grande en muy poco tiempo. Marcamos esas lecturas como sospechosas para revisarlas.'
    default:
      return `El detector marcó esta actividad como sospechosa: ${alerta.regla}. Revisa la alerta y confirma si fue esperada.`
  }
}

function duracionDeAlerta(alerta: AlertaSeguridad): string | null {
  return alerta.regla_id === ID_FUERZA_BRUTA ? '60 minutos' : null
}

function intentosDeAlerta(detalle: Record<string, unknown>): string | null {
  const intentos = detalle.intentos
  return typeof intentos === 'number' || typeof intentos === 'string'
    ? String(intentos)
    : null
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
            const intentos = intentosDeAlerta(alerta.detalle)
            const duracion = duracionDeAlerta(alerta)

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
                    {etiquetaAccion(alerta.accion)}
                  </p>

                  <details className="security__details">
                    <summary>¿Qué pasó?</summary>
                    <div className="security__explicacion">
                      <p>{explicacionDeAlerta(alerta)}</p>
                      <dl className="security__datos">
                        <div>
                          <dt>IP</dt>
                          <dd>{alerta.ip_origen ?? 'Desconocida'}</dd>
                        </div>
                        {intentos && (
                          <div>
                            <dt>Intentos</dt>
                            <dd>{intentos}</dd>
                          </div>
                        )}
                        <div>
                          <dt>Acción</dt>
                          <dd>{etiquetaAccion(alerta.accion)}</dd>
                        </div>
                        {duracion && (
                          <div>
                            <dt>Duración</dt>
                            <dd>{duracion}</dd>
                          </div>
                        )}
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
