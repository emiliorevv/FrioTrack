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
      nota: 'Últimas 24 h',
      tono: 'ok',
    },
    {
      id: 'alertas_activas',
      label: 'Alertas activas',
      valor: String(kpis.alertas_activas),
      nota:
        kpis.alertas_activas === 1
          ? '1 pendiente de atender'
          : `${kpis.alertas_activas} pendientes de atender`,
      tono: 'warn',
    },
    {
      id: 'tiempo_respuesta_promedio_min',
      label: 'Tiempo de respuesta',
      valor: `${kpis.tiempo_respuesta_promedio_min.toFixed(1)} min`,
      nota: 'Promedio del día',
      tono: 'ok',
    },
    {
      id: 'valor_en_riesgo_mxn',
      label: 'Valor en riesgo',
      valor: formatearMxn(kpis.valor_en_riesgo_mxn),
      nota:
        kpis.valor_en_riesgo_mxn > 0
          ? 'Producto en riesgo'
          : 'Sin producto en riesgo',
      tono: 'warn',
    },
    {
      id: 'merma_hoy_mxn',
      label: 'Merma hoy',
      valor: formatearMxn(kpis.merma_hoy_mxn),
      nota:
        kpis.merma_hoy_mxn > 0 ? 'Pérdida registrada hoy' : 'Sin pérdidas hoy',
      tono: 'ok',
    },
    {
      id: 'merma_mes_mxn',
      label: 'Merma del mes',
      valor: formatearMxn(kpis.merma_mes_mxn),
      nota: 'Acumulado del mes',
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
