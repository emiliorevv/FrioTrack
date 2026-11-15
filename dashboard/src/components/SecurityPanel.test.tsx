import { fireEvent, render, screen } from '@testing-library/react'
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
  detalle: {
    clave: 'ip:187.190.12.4',
    intentos: 12,
    ventana: '5 min',
    ruta: '/api/telemetria',
  },
  accion: 'bloquear_ip',
}

const alertaToken: AlertaSeguridad = {
  ...alerta,
  id: 2,
  regla_id: 'e26aa409-804c-47fb-b852-1786ddaa172d',
  regla: 'Token de sensor desde IP desconocida',
  ip_origen: '203.0.113.9',
  detalle: { clave: 'sensor:S-PES-01' },
  accion: 'revocar_token',
}

const alertaLecturas: AlertaSeguridad = {
  ...alerta,
  id: 3,
  regla_id: '26f277c2-6d7a-4ff2-b44c-452f2788f824',
  regla: 'Lecturas imposibles de temperatura',
  ip_origen: null,
  detalle: { sensor: 'S-PES-01', cambio: '8.6 °C' },
  accion: 'marcar_lecturas',
}

afterEach(() => {
  vi.useRealTimers()
})

function abrirExplicacion() {
  const resumen = screen.getByText('¿Qué pasó?')
  const details = resumen.closest('details')
  expect(details).not.toBeNull()
  fireEvent.click(resumen)
  return details as HTMLDetailsElement
}

describe('SecurityPanel', () => {
  it('deriva título, severidad, IP y acción de la alerta', () => {
    render(<SecurityPanel alertas={[alerta]} cargado error={null} />)

    expect(screen.getByText('Fuerza bruta de tokens')).toBeInTheDocument()
    expect(screen.getByText('Alta')).toBeInTheDocument()
    expect(screen.getByText('187.190.12.4 · IP bloqueada')).toBeInTheDocument()
    expect(screen.queryByText(/clave:/)).not.toBeInTheDocument()
  })

  it('muestra el tiempo relativo de la alerta', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-12T16:45:00-06:00'))

    render(<SecurityPanel alertas={[alerta]} cargado error={null} />)

    expect(screen.getByText('hace 3 min')).toBeInTheDocument()
  })

  it('abre y cierra la explicación de fuerza bruta', () => {
    render(<SecurityPanel alertas={[alerta]} cargado error={null} />)

    const details = abrirExplicacion()
    expect(details.open).toBe(true)
    expect(
      screen.getByText(
        'Detectamos varios intentos fallidos de inicio de sesión desde la misma dirección. Para proteger el sistema, bloqueamos esa IP durante 60 minutos.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('60 minutos')).toBeInTheDocument()

    fireEvent.click(screen.getByText('¿Qué pasó?'))
    expect(details.open).toBe(false)
  })

  it('explica el token de sensor usado desde una IP desconocida', () => {
    render(<SecurityPanel alertas={[alertaToken]} cargado error={null} />)

    abrirExplicacion()

    expect(
      screen.getByText(
        'Un sensor válido se usó desde una red que no es la del restaurante. Revocamos su token para evitar lecturas falsas.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('203.0.113.9', { selector: 'dd' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Token revocado', { selector: 'dd' }),
    ).toBeInTheDocument()
  })

  it('explica las lecturas imposibles', () => {
    render(<SecurityPanel alertas={[alertaLecturas]} cargado error={null} />)

    abrirExplicacion()

    expect(
      screen.getByText(
        'Una cámara reportó un cambio de temperatura demasiado grande en muy poco tiempo. Marcamos esas lecturas como sospechosas para revisarlas.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Origen desconocido · Lecturas marcadas'),
    ).toBeInTheDocument()
  })

  it('usa un texto genérico para una regla desconocida', () => {
    const generica: AlertaSeguridad = {
      ...alerta,
      id: 4,
      regla_id: 'regla-nueva',
      regla: 'Regla nueva',
    }

    render(<SecurityPanel alertas={[generica]} cargado error={null} />)

    abrirExplicacion()

    expect(
      screen.getByText(
        'El detector marcó esta actividad como sospechosa: Regla nueva. Revisa la alerta y confirma si fue esperada.',
      ),
    ).toBeInTheDocument()
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
    expect(screen.getAllByText(/Sin acción/).length).toBeGreaterThan(0)
  })
})
