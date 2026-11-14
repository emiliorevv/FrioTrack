import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Camara } from '../types'
import { CameraCard } from './CameraCard'

const camaraSinLecturas: Camara = {
  id: 9,
  nombre: 'Cámara nueva',
  rango_min_c: 0,
  rango_max_c: 4,
  min_para_riesgo: 15,
  min_para_merma: 120,
  estado: 'en_rango',
  ultima_lectura: null,
  valor_en_riesgo_mxn: 0,
}

const camaraConLectura: Camara = {
  ...camaraSinLecturas,
  id: 10,
  nombre: 'Pescados y mariscos',
  estado: 'alerta',
  ultima_lectura: {
    ts: '2026-11-14T11:59:55Z',
    temperatura_c: 3.1,
    humedad_pct: 85,
    puerta_abierta: false,
  },
}

afterEach(() => {
  vi.useRealTimers()
})

describe('CameraCard', () => {
  it('muestra "Sin lecturas" y no pinta temperatura ni sparkline', () => {
    const { container } = render(
      <CameraCard camara={camaraSinLecturas} serie={[1, 2, 3]} />,
    )

    expect(screen.getByText('Sin lecturas')).toBeInTheDocument()
    expect(screen.getByText('Sin dato')).toBeInTheDocument()
    expect(
      container.querySelector('.camera-card__temperature'),
    ).not.toBeInTheDocument()
    expect(container.querySelector('.sparkline')).not.toBeInTheDocument()
  })

  it('muestra el tiempo relativo de la última lectura', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-14T12:00:00Z'))

    render(<CameraCard camara={camaraConLectura} serie={[3, 3.1]} />)

    expect(screen.getByText('hace 5 s')).toBeInTheDocument()
  })
})
