import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Header } from './Header'

describe('Header', () => {
  it('no muestra la pill de demo cuando la escala es 1', () => {
    render(<Header actualizadoHaceSegundos={8} escalaTiempo={1} />)

    expect(screen.queryByText(/MODO DEMO/)).not.toBeInTheDocument()
  })

  it('no muestra la pill de demo cuando la escala no está definida', () => {
    render(<Header actualizadoHaceSegundos={8} />)

    expect(screen.queryByText(/MODO DEMO/)).not.toBeInTheDocument()
  })

  it('muestra la pill con la escala cuando es distinta de 1', () => {
    render(<Header actualizadoHaceSegundos={8} escalaTiempo={30} />)

    expect(screen.getByText('MODO DEMO ×30')).toBeInTheDocument()
  })

  it('usa las iniciales recibidas y el default JC', () => {
    const { rerender } = render(<Header actualizadoHaceSegundos={8} />)

    expect(
      screen.getByRole('img', { name: 'Sesión de JC, jefe de cocina' }),
    ).toHaveTextContent('JC')

    rerender(<Header actualizadoHaceSegundos={8} iniciales="AM" />)

    expect(
      screen.getByRole('img', { name: 'Sesión de AM, jefe de cocina' }),
    ).toHaveTextContent('AM')
  })
})
