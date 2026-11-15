import { fireEvent, render, screen } from '@testing-library/react'
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

afterEach(() => {
  vi.useRealTimers()
})

describe('AlertasActivas', () => {
  it('lista la alerta con cámara, tipo, temperatura y tiempo relativo', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-14T12:00:00Z'))

    render(
      <AlertasActivas
        alertas={[alerta]}
        camaras={[camara]}
        cargando={false}
        error={null}
        atendiendo={{}}
        onAtender={() => {}}
      />,
    )

    expect(
      screen.getByRole('heading', { name: /Alertas activas/ }),
    ).toBeInTheDocument()
    expect(screen.getByText('Pescados y mariscos')).toBeInTheDocument()
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    expect(screen.getByText(/Máx\. 3\.4 °C/)).toBeInTheDocument()
    expect(screen.getByText('hace 3 min')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Atender' })).toBeEnabled()
  })

  it('muestra el estado vacío sin alertas', () => {
    render(
      <AlertasActivas
        alertas={[]}
        camaras={[]}
        cargando={false}
        error={null}
        atendiendo={{}}
        onAtender={() => {}}
      />,
    )

    expect(screen.getByText('Sin alertas activas')).toBeInTheDocument()
  })

  it('muestra la carga inicial sin confundirla con el vacío', () => {
    render(
      <AlertasActivas
        alertas={[]}
        camaras={[]}
        cargando
        error={null}
        atendiendo={{}}
        onAtender={() => {}}
      />,
    )

    expect(screen.getByText('Cargando alertas…')).toBeInTheDocument()
    expect(screen.queryByText('Sin alertas activas')).not.toBeInTheDocument()
  })

  it('llama al atender con el id de la alerta', () => {
    const onAtender = vi.fn()
    render(
      <AlertasActivas
        alertas={[alerta]}
        camaras={[camara]}
        cargando={false}
        error={null}
        atendiendo={{}}
        onAtender={onAtender}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Atender' }))

    expect(onAtender).toHaveBeenCalledWith(31)
  })

  it('deshabilita y muestra “Atendiendo…” mientras atiende', () => {
    render(
      <AlertasActivas
        alertas={[alerta]}
        camaras={[camara]}
        cargando={false}
        error={null}
        atendiendo={{ 31: true }}
        onAtender={() => {}}
      />,
    )

    const boton = screen.getByRole('button', { name: 'Atendiendo…' })
    expect(boton).toBeDisabled()
    expect(boton).toHaveAttribute('aria-busy', 'true')
  })

  it('marca como atendida una alerta ya gestionada', () => {
    render(
      <AlertasActivas
        alertas={[{ ...alerta, atendida_por: 3 }]}
        camaras={[camara]}
        cargando={false}
        error={null}
        atendiendo={{}}
        onAtender={() => {}}
      />,
    )

    expect(screen.getByRole('button', { name: 'Atendida' })).toBeDisabled()
  })

  it('muestra error al cargar en vez de “Sin alertas”', () => {
    render(
      <AlertasActivas
        alertas={[]}
        camaras={[]}
        cargando={false}
        error="La API no responde"
        atendiendo={{}}
        onAtender={() => {}}
      />,
    )

    expect(
      screen.getByText('No se pudieron cargar las alertas activas.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Sin alertas activas')).not.toBeInTheDocument()
  })

  it('conserva la lista y avisa si falla una actualización', () => {
    render(
      <AlertasActivas
        alertas={[alerta]}
        camaras={[camara]}
        cargando={false}
        error="La API no responde"
        atendiendo={{}}
        onAtender={() => {}}
      />,
    )

    expect(
      screen.getByText(/No se pudieron actualizar las alertas activas/),
    ).toBeInTheDocument()
    expect(screen.getByText('Pescados y mariscos')).toBeInTheDocument()
  })
})
