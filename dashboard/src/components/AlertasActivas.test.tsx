import { fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AlertaOperativa, Camara } from '../types'
import { AlertasActivas } from './AlertasActivas'

const camara: Camara = {
  id: 1,
  nombre: 'Pescados y mariscos',
  rango_min_c: 0,
  rango_max_c: 2,
  min_para_riesgo: 10,
  min_para_merma: 60,
  estado: 'alerta',
  ultima_lectura: {
    ts: '2026-11-14T11:59:00Z',
    temperatura_c: 3.4,
    humedad_pct: 85,
    puerta_abierta: false,
  },
  valor_en_riesgo_mxn: 0,
  valor_inventario_mxn: 0,
}

const alerta: AlertaOperativa = {
  id: 31,
  camara_id: 1,
  tipo: 'temperatura',
  abierta_en: '2026-11-14T11:57:00Z',
  cerrada_en: null,
  atendida_por: null,
  temperatura_max_c: 3.4,
  sms_enviados: 1,
}

type Props = ComponentProps<typeof AlertasActivas>

function renderizar(props: Partial<Props> = {}) {
  return render(
    <AlertasActivas
      alertas={[]}
      camaras={[]}
      cargando={false}
      error={null}
      errorAtender={null}
      atendiendo={{}}
      puedeAtender
      onAtender={() => {}}
      onLimpiarErrorAtender={() => {}}
      {...props}
    />,
  )
}

afterEach(() => {
  vi.useRealTimers()
})

describe('AlertasActivas', () => {
  it('lista la alerta con cámara, tipo, temperatura y tiempo relativo', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-14T12:00:00Z'))

    renderizar({ alertas: [alerta], camaras: [camara] })

    expect(
      screen.getByRole('heading', { name: /Alertas activas/ }),
    ).toHaveTextContent('1')
    expect(screen.getByText('1 pendiente de atención')).toBeInTheDocument()
    expect(screen.getByText('Pescados y mariscos')).toBeInTheDocument()
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    expect(screen.getByText(/Máx\. 3\.4 °C/)).toBeInTheDocument()
    expect(screen.getByText('hace 3 min')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Atender' })).toBeEnabled()
  })

  it('no mete el tiempo relativo en una región live; anuncia solo el conteo', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-14T12:00:00Z'))

    renderizar({ alertas: [alerta], camaras: [camara] })

    expect(screen.getByText('hace 3 min').closest('[aria-live]')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent(
      '1 activa; 1 pendiente de atención',
    )
  })

  it('muestra el estado vacío sin alertas', () => {
    renderizar()

    expect(screen.getByText('Sin alertas activas')).toBeInTheDocument()
    expect(screen.getByText('0 pendientes de atención')).toBeInTheDocument()
  })

  it('muestra la carga inicial sin confundirla con el vacío', () => {
    const { container } = renderizar({ cargando: true })

    expect(
      container.querySelector('.alertas-activas__empty'),
    ).toHaveTextContent('Cargando alertas…')
    expect(screen.getByRole('status')).toHaveTextContent('Cargando alertas…')
    expect(screen.queryByText('Sin alertas activas')).not.toBeInTheDocument()
  })

  it('llama al atender con el id de la alerta', () => {
    const onAtender = vi.fn()
    renderizar({ alertas: [alerta], camaras: [camara], onAtender })

    fireEvent.click(screen.getByRole('button', { name: 'Atender' }))

    expect(onAtender).toHaveBeenCalledWith(31)
  })

  it('deshabilita y muestra “Atendiendo…” mientras atiende', () => {
    renderizar({
      alertas: [alerta],
      camaras: [camara],
      atendiendo: { 31: true },
    })

    const boton = screen.getByRole('button', { name: 'Atendiendo…' })
    expect(boton).toBeDisabled()
    expect(boton).toHaveAttribute('aria-busy', 'true')
  })

  it('distingue las atendidas de las pendientes', () => {
    renderizar({
      alertas: [{ ...alerta, atendida_por: 3 }],
      camaras: [camara],
    })

    expect(screen.getByRole('button', { name: 'Atendida' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Atendida' })).toHaveAttribute(
      'aria-busy',
      'false',
    )
    expect(screen.getByText('0 pendientes de atención')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: /Alertas activas/ }),
    ).toHaveTextContent('1')
  })

  it('el gerente ve el botón deshabilitado y la nota de rol', () => {
    renderizar({
      alertas: [alerta],
      camaras: [camara],
      puedeAtender: false,
    })

    const boton = screen.getByRole('button', { name: 'Atender' })
    expect(boton).toBeDisabled()
    expect(boton).toHaveAttribute('aria-describedby', 'alertas-permiso')
    expect(
      screen.getByText('Solo jefe de cocina puede atender.'),
    ).toBeInTheDocument()
  })

  it('muestra error al cargar en vez de “Sin alertas”', () => {
    renderizar({ error: 'La API no responde' })

    expect(
      screen.getByText('No se pudieron cargar las alertas activas.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Sin alertas activas')).not.toBeInTheDocument()
  })

  it('conserva la lista y avisa si falla una actualización', () => {
    renderizar({
      alertas: [alerta],
      camaras: [camara],
      error: 'La API no responde',
    })

    expect(
      screen.getByText(/No se pudieron actualizar las alertas activas/),
    ).toBeInTheDocument()
    expect(screen.getByText('Pescados y mariscos')).toBeInTheDocument()
  })

  it('muestra el detail de atender y lo puede cerrar', () => {
    const onLimpiarErrorAtender = vi.fn()
    renderizar({
      alertas: [alerta],
      camaras: [camara],
      errorAtender:
        'No hay un usuario con rol jefe_cocina; carga el seed para poder atender alertas.',
      onLimpiarErrorAtender,
    })

    const alertaError = screen.getByRole('alert')
    expect(alertaError).toHaveTextContent(
      'No hay un usuario con rol jefe_cocina',
    )
    expect(
      screen.queryByText(/No se pudieron actualizar las alertas activas/),
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(onLimpiarErrorAtender).toHaveBeenCalledTimes(1)
  })
})
