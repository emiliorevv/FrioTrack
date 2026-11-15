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
    rutas: ['/api/telemetria'],
    intentos: 12,
    ventana_s: 300,
  },
  accion: 'bloquear_ip',
}

const alertaTokenConSensor: AlertaSeguridad = {
  ...alerta,
  id: 2,
  regla_id: 'e26aa409-804c-47fb-b852-1786ddaa172d',
  regla: 'Token de sensor desde IP desconocida',
  ip_origen: '203.0.113.9',
  detalle: { clave: 'sensor:S-PES-01', sensor_id: 'S-PES-01' },
  accion: 'revocar_token',
}

const alertaTokenSinSensor: AlertaSeguridad = {
  ...alertaTokenConSensor,
  id: 5,
  detalle: { clave: 'sensor:S-PES-01' },
}

const alertaLecturas: AlertaSeguridad = {
  ...alerta,
  id: 3,
  regla_id: '26f277c2-6d7a-4ff2-b44c-452f2788f824',
  regla: 'Lecturas imposibles de temperatura',
  ip_origen: null,
  detalle: {
    camara_id: 3,
    temperatura_anterior_c: 2,
    temperatura_c: 12,
    delta_c: 10,
    segundos: 45,
  },
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

  it('explica fuerza bruta sin inventar la duración del bloqueo', () => {
    render(<SecurityPanel alertas={[alerta]} cargado error={null} />)

    const details = abrirExplicacion()
    expect(details.open).toBe(true)
    expect(
      screen.getByText(
        'Detectamos muchos intentos rechazados seguidos desde la misma dirección (inicios de sesión o envíos de telemetría). Para proteger el sistema, bloqueamos esa IP durante el tiempo configurado.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('5 min')).toBeInTheDocument()
    expect(screen.getByText('/api/telemetria')).toBeInTheDocument()
    expect(screen.queryByText('60 minutos')).not.toBeInTheDocument()
    expect(screen.queryByText('Duración')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('¿Qué pasó?'))
    expect(details.open).toBe(false)
  })

  it('explica el token revocado e identifica el sensor', () => {
    render(
      <SecurityPanel alertas={[alertaTokenConSensor]} cargado error={null} />,
    )

    abrirExplicacion()

    expect(
      screen.getByText(
        'El sensor S-PES-01 autenticó una lectura desde una red desconocida. Revocamos su token para evitar lecturas falsas.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('S-PES-01')).toBeInTheDocument()
    expect(
      screen.getByText('Token revocado', { selector: 'dd' }),
    ).toBeInTheDocument()
  })

  it('no afirma una revocación si la alerta no identificó el sensor', () => {
    render(
      <SecurityPanel alertas={[alertaTokenSinSensor]} cargado error={null} />,
    )

    abrirExplicacion()

    expect(
      screen.getByText(
        'Detectamos un token de sensor usado desde una red desconocida, pero la alerta no identificó el sensor; no se revocó ningún token. Revisa los accesos recientes.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('203.0.113.9 · Sin revocación')).toBeInTheDocument()
    expect(screen.queryByText('Token revocado')).not.toBeInTheDocument()
  })

  it('muestra cámara, temperaturas y delta en lecturas imposibles', () => {
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
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('2.0 °C')).toBeInTheDocument()
    expect(screen.getByText('12.0 °C')).toBeInTheDocument()
    expect(screen.getByText('10.0 °C')).toBeInTheDocument()
    expect(screen.getByText('45 s')).toBeInTheDocument()
    expect(screen.queryByText('IP')).not.toBeInTheDocument()
  })

  it('usa la descripción del backend como fuente principal', () => {
    const conDescripcion: AlertaSeguridad = {
      ...alerta,
      descripcion: 'Descripción enviada por el backend.',
    }

    render(<SecurityPanel alertas={[conDescripcion]} cargado error={null} />)
    abrirExplicacion()

    expect(
      screen.getByText('Descripción enviada por el backend.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText(/Detectamos muchos intentos rechazados/),
    ).not.toBeInTheDocument()
  })

  it('acepta la descripción dentro de detalle como fallback', () => {
    const conDescripcionDetalle: AlertaSeguridad = {
      ...alerta,
      detalle: { ...alerta.detalle, descripcion: 'Descripción en el detalle.' },
    }

    render(
      <SecurityPanel alertas={[conDescripcionDetalle]} cargado error={null} />,
    )
    abrirExplicacion()

    expect(screen.getByText('Descripción en el detalle.')).toBeInTheDocument()
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
