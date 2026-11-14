import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Header } from './Header'

afterEach(() => {
  vi.useRealTimers()
})

describe('Header', () => {
  it('no muestra la pill de demo cuando la escala es 1', () => {
    render(<Header actualizadoEn={null} escalaTiempo={1} />)

    expect(screen.queryByText(/MODO DEMO/)).not.toBeInTheDocument()
  })

  it('no muestra la pill de demo cuando la escala no está definida', () => {
    render(<Header actualizadoEn={null} />)

    expect(screen.queryByText(/MODO DEMO/)).not.toBeInTheDocument()
  })

  it('muestra la pill con la escala cuando es distinta de 1', () => {
    render(<Header actualizadoEn={null} escalaTiempo={30} />)

    expect(screen.getByText('MODO DEMO ×30')).toBeInTheDocument()
  })

  it('sin datos no inventa "Actualizado hace 0 s"', () => {
    render(<Header actualizadoEn={null} />)

    expect(screen.getByText('Sin datos')).toBeInTheDocument()
    expect(screen.queryByText(/Actualizado hace/)).not.toBeInTheDocument()
  })

  it('muestra y actualiza los segundos desde la última actualización', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-14T12:00:00Z'))

    render(<Header actualizadoEn={new Date('2026-11-14T11:59:52Z')} />)

    expect(screen.getByText('Actualizado hace 8 s')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(screen.getByText('Actualizado hace 10 s')).toBeInTheDocument()
  })

  it('usa las iniciales recibidas y el default JC', () => {
    const { rerender } = render(<Header actualizadoEn={null} />)

    expect(
      screen.getByRole('img', { name: 'Sesión de JC, jefe de cocina' }),
    ).toHaveTextContent('JC')

    rerender(<Header actualizadoEn={null} iniciales="AM" />)

    expect(
      screen.getByRole('img', { name: 'Sesión de AM, jefe de cocina' }),
    ).toHaveTextContent('AM')
  })
})
