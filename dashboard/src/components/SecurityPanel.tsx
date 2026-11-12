import type { AlertaSeguridad } from '../types'
import { formatearHace } from '../lib/format'

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
        {alertas.map((alerta) => (
          <li className="security__item" key={alerta.id}>
            <span
              className={`security__dot security__dot--${alerta.tono}`}
              aria-hidden="true"
            />
            <div className="security__body">
              <p className="security__title">
                {alerta.titulo}
                <span className={`tag tag--${alerta.tono}`}>
                  {alerta.etiqueta}
                </span>
              </p>
              <p className="security__detail">{alerta.detalle}</p>
            </div>
            <time className="security__time" dateTime={alerta.ts}>
              {formatearHace(alerta.ts, ahora)}
            </time>
          </li>
        ))}
      </ul>
    </section>
  )
}
