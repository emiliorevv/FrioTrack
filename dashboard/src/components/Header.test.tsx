import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Header } from './Header'

const sesion = {
  usuario: 'jefe',
  rol: 'jefe_cocina',
  onLogout: () => {},
}

afterEach(() => {
  vi.useRealTimers()
})

describe('Header', () => {
  it('no muestra la pill de demo cuando la escala es 1', () => {
    render(<Header actualizadoEn={null} escalaTiempo={1} {...sesion} />)

    expect(screen.queryByText(/MODO DEMO/)).not.toBeInTheDocument()
  })

  it('no muestra la pill de demo cuando la escala no está definida', () => {
    render(<Header actualizadoEn={null} {...sesion} />)

    expect(screen.queryByText(/MODO DEMO/)).not.toBeInTheDocument()
  })

  it('muestra la pill con la escala cuando es distinta de 1', () => {
    render(<Header actualizadoEn={null} escalaTiempo={30} {...sesion} />)

    expect(screen.getByText('MODO DEMO ×30')).toBeInTheDocument()
  })

  it('sin datos no inventa "Actualizado hace 0 s"', () => {
    render(<Header actualizadoEn={null} {...sesion} />)

    expect(screen.getByText('Sin datos')).toBeInTheDocument()
    expect(screen.queryByText(/Actualizado hace/)).not.toBeInTheDocument()
  })

  it('muestra y actualiza los segundos desde la última actualización', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-14T12:00:00Z'))

    render(
      <Header actualizadoEn={new Date('2026-11-14T11:59:52Z')} {...sesion} />,
    )

    expect(screen.getByText('Actualizado hace 8 s')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(screen.getByText('Actualizado hace 10 s')).toBeInTheDocument()
  })

  it('muestra iniciales, usuario y rol del jefe', () => {
    render(<Header actualizadoEn={null} {...sesion} />)

    expect(
      screen.getByRole('img', { name: 'Sesión de jefe, Jefe de cocina' }),
    ).toHaveTextContent('JE')
    expect(screen.getByText('jefe')).toBeInTheDocument()
    expect(screen.getByText('Jefe de cocina')).toBeInTheDocument()
  })

  it('actualiza iniciales y rol para el gerente', () => {
    render(
      <Header
        actualizadoEn={null}
        usuario="gerente"
        rol="gerente"
        onLogout={() => {}}
      />,
    )

    expect(
      screen.getByRole('img', { name: 'Sesión de gerente, Gerente' }),
    ).toHaveTextContent('GE')
    expect(screen.getByText('Gerente')).toBeInTheDocument()
  })

  it('el botón Salir llama al logout y su nombre accesible coincide', () => {
    const onLogout = vi.fn()
    render(<Header actualizadoEn={null} {...sesion} onLogout={onLogout} />)

    fireEvent.click(screen.getByRole('button', { name: 'Salir' }))

    expect(onLogout).toHaveBeenCalledTimes(1)
  })
})
