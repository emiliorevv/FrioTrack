import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
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

describe('SecurityPanel', () => {
  it('deriva título, severidad, acción y resumen del detalle', () => {
    render(
      <SecurityPanel
        alertas={[alerta]}
        ahora={new Date('2026-11-12T16:45:00-06:00')}
      />,
    )

    expect(screen.getByText('Fuerza bruta de tokens')).toBeInTheDocument()
    expect(screen.getByText('Alta')).toBeInTheDocument()
    expect(
      screen.getByText(
        '187.190.12.4 · intentos: 12 · ventana: 5 min · ruta: /api/telemetria · IP bloqueada',
      ),
    ).toBeInTheDocument()
  })
})
