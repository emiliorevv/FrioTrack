import type { Kpis } from '../types'
import { formatearMxn } from '../lib/format'

type TonoKpi = 'ok' | 'warn' | 'neutral'

interface KpiItem {
  id: keyof Kpis
  label: string
  valor: string
  nota: string
  tono: TonoKpi
}

interface KpiStripProps {
  kpis: Kpis
}

export function KpiStrip({ kpis }: KpiStripProps) {
  const items: KpiItem[] = [
    {
      id: 'pct_tiempo_en_rango_24h',
      label: '% en rango 24 h',
      valor: `${kpis.pct_tiempo_en_rango_24h.toFixed(1)}%`,
      nota: '+1.8 pts vs. ayer',
      tono: 'ok',
    },
    {
      id: 'alertas_activas',
      label: 'Alertas activas',
      valor: String(kpis.alertas_activas),
      nota: '1 pendiente de atender',
      tono: 'warn',
    },
    {
      id: 'tiempo_respuesta_promedio_min',
      label: 'Tiempo de respuesta',
      valor: `${kpis.tiempo_respuesta_promedio_min.toFixed(1)} min`,
      nota: 'Bajo la meta de 10 min',
      tono: 'ok',
    },
    {
      id: 'valor_en_riesgo_mxn',
      label: 'Valor en riesgo',
      valor: formatearMxn(kpis.valor_en_riesgo_mxn),
      nota: '2 lotes · Pescados',
      tono: 'warn',
    },
    {
      id: 'merma_hoy_mxn',
      label: 'Merma hoy',
      valor: formatearMxn(kpis.merma_hoy_mxn),
      nota: 'Sin pérdidas hoy',
      tono: 'ok',
    },
    {
      id: 'merma_mes_mxn',
      label: 'Merma del mes',
      valor: formatearMxn(kpis.merma_mes_mxn),
      nota: '−12% vs. octubre',
      tono: 'neutral',
    },
  ]

  return (
    <dl className="kpi-strip">
      {items.map((item) => (
        <div className={`kpi kpi--${item.tono}`} key={item.id}>
          <dt className="kpi__label">{item.label}</dt>
          <dd className="kpi__value">
            {item.valor}
            <span className="kpi__note">{item.nota}</span>
          </dd>
        </div>
      ))}
    </dl>
  )
}
