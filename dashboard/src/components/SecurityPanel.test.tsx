import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AlertaSeguridad } from '../types'
import { SecurityPanel } from './SecurityPanel'

const alerta: AlertaSeguridad = {
  id: 1,
  regla_id: '3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41',
  regla: 'Fuerza bruta de tokens',
  severidad: 'high',
  ts: '2026-11-12T16:42:00-06:00',
  ip_origen: '187.190.12.4',
  detalle: { intentos: 12, ventana: '5 min', ruta: '/api/telemetria' },
  accion: 'bloquear_ip',
}

afterEach(() => {
  vi.useRealTimers()
})

describe('SecurityPanel', () => {
  it('deriva título, severidad, acción y resumen del detalle', () => {
    render(<SecurityPanel alertas={[alerta]} cargado error={null} />)

    expect(screen.getByText('Fuerza bruta de tokens')).toBeInTheDocument()
    expect(screen.getByText('Alta')).toBeInTheDocument()
    expect(
      screen.getByText(
        '187.190.12.4 · intentos: 12 · ventana: 5 min · ruta: /api/telemetria · IP bloqueada',
      ),
    ).toBeInTheDocument()
  })

  it('muestra el tiempo relativo de la alerta', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-12T16:45:00-06:00'))

    render(<SecurityPanel alertas={[alerta]} cargado error={null} />)

    expect(screen.getByText('hace 3 min')).toBeInTheDocument()
  })

  it('muestra el estado vacío cuando no hay alertas', () => {
    render(<SecurityPanel alertas={[]} cargado error={null} />)

    expect(screen.getByText('Sin alertas del detector.')).toBeInTheDocument()
    expect(screen.queryByText(/Datos de ejemplo/)).not.toBeInTheDocument()
  })

  it('distingue la carga en curso del estado vacío', () => {
    render(<SecurityPanel alertas={[]} cargado={false} error={null} />)

    expect(
      screen.getByText('Cargando alertas del detector…'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Sin alertas del detector.'),
    ).not.toBeInTheDocument()
  })

  it('muestra un error distinto cuando no se pudieron cargar', () => {
    render(
      <SecurityPanel alertas={[]} cargado={false} error="La API no responde" />,
    )

    expect(
      screen.getByText('No se pudieron cargar las alertas del detector.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Sin alertas del detector.'),
    ).not.toBeInTheDocument()
  })

  it('conserva las alertas previas y avisa si falló una actualización', () => {
    render(
      <SecurityPanel alertas={[alerta]} cargado error="La API no responde" />,
    )

    expect(screen.getByText('Fuerza bruta de tokens')).toBeInTheDocument()
    expect(
      screen.getByText(/No se pudieron actualizar las alertas/),
    ).toBeInTheDocument()
  })

  it('no rompe con una severidad o acción desconocidas', () => {
    const rara: AlertaSeguridad = {
      ...alerta,
      severidad: 'informational',
      accion: 'notificar',
    }

    render(<SecurityPanel alertas={[rara]} cargado error={null} />)

    expect(screen.getByText('Desconocida')).toBeInTheDocument()
    expect(screen.getByText(/Sin acción/)).toBeInTheDocument()
  })
})
