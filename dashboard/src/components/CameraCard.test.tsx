import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
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

describe('CameraCard', () => {
  it('muestra "Sin lecturas" y no pinta temperatura ni sparkline', () => {
    const { container } = render(
      <CameraCard
        camara={camaraSinLecturas}
        serie={[1, 2, 3]}
        ahora={new Date('2026-11-12T16:45:00-06:00')}
      />,
    )

    expect(screen.getByText('Sin lecturas')).toBeInTheDocument()
    expect(screen.getByText('Sin dato')).toBeInTheDocument()
    expect(
      container.querySelector('.camera-card__temperature'),
    ).not.toBeInTheDocument()
    expect(container.querySelector('.sparkline')).not.toBeInTheDocument()
  })
})
