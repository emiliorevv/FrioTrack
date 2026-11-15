import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Kpis } from '../types'
import { KpiStrip } from './KpiStrip'

const kpisBase: Kpis = {
  pct_tiempo_en_rango_24h: 97.3,
  alertas_activas: 1,
  tiempo_respuesta_promedio_min: 6.5,
  valor_en_riesgo_mxn: 4850,
  merma_hoy_mxn: 0,
  merma_mes_mxn: 1720,
}

const AYUDA_TIEMPO =
  'Promedio de minutos entre que se abre una alerta y el jefe la marca como atendida. No mide la recuperación de la cámara.'
const AYUDA_RIESGO =
  'Costo del producto que está ahora en cámaras fuera de rango o con la puerta abierta demasiado tiempo.'

describe('KpiStrip', () => {
  it('deriva las notas de los valores y no compara contra periodos', () => {
    render(<KpiStrip kpis={kpisBase} />)

    expect(screen.getByText('Últimas 24 h')).toBeInTheDocument()
    expect(screen.getByText('1 pendiente de atender')).toBeInTheDocument()
    expect(screen.getByText('Promedio del día')).toBeInTheDocument()
    expect(screen.getByText('Producto en riesgo')).toBeInTheDocument()
    expect(screen.getByText('Sin pérdidas hoy')).toBeInTheDocument()
    expect(screen.getByText('Acumulado del mes')).toBeInTheDocument()
    expect(
      screen.queryByText(/vs\. ayer|vs\. octubre|Bajo la meta|2 lotes/),
    ).not.toBeInTheDocument()
  })

  it('usa plural y los estados en cero', () => {
    render(
      <KpiStrip
        kpis={{
          ...kpisBase,
          alertas_activas: 3,
          valor_en_riesgo_mxn: 0,
          merma_hoy_mxn: 250,
        }}
      />,
    )

    expect(screen.getByText('3 pendientes de atender')).toBeInTheDocument()
    expect(screen.getByText('Sin producto en riesgo')).toBeInTheDocument()
    expect(screen.getByText('Pérdida registrada hoy')).toBeInTheDocument()
  })

  it('muestra la ayuda accesible de cada KPI', () => {
    render(<KpiStrip kpis={kpisBase} />)

    for (const label of [
      '% en rango 24 h',
      'Alertas activas',
      'Tiempo de respuesta',
      'Valor en riesgo',
      'Merma hoy',
      'Merma del mes',
    ]) {
      const boton = screen.getByRole('button', {
        name: `Qué significa: ${label}`,
      })
      expect(boton).toHaveTextContent('?')
      expect(boton).toHaveAttribute('data-tip')
    }

    expect(screen.getByText(AYUDA_TIEMPO)).toBeInTheDocument()
    expect(screen.getByText(AYUDA_RIESGO)).toBeInTheDocument()
    expect(
      screen.getByRole('button', {
        name: 'Qué significa: Tiempo de respuesta',
      }),
    ).toHaveAttribute('data-tip', AYUDA_TIEMPO)
  })
})
