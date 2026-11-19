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

  it('explica la escala en la pill y en el texto accesible', () => {
    render(<Header actualizadoEn={null} escalaTiempo={30} {...sesion} />)

    const pill = screen.getByTitle(
      'Los tiempos de las reglas se aceleran ×30: 1 minuto de regla equivale a 2 segundos reales.',
    )
    expect(pill).toHaveTextContent(
      'MODO DEMO ×30 · 1 min de regla = 2 s reales',
    )
    expect(pill).not.toHaveAttribute('aria-label')
    expect(
      screen.getByText(
        'Los tiempos de las reglas se aceleran ×30: 1 minuto de regla equivale a 2 segundos reales.',
      ),
    ).toHaveClass('visually-hidden')
    expect(pill.querySelector('.demo-pill__detalle')).toHaveTextContent(
      '· 1 min de regla = 2 s reales',
    )
  })

  it('formatea decimales, segundos y milisegundos', () => {
    const { rerender } = render(
      <Header actualizadoEn={null} escalaTiempo={24} {...sesion} />,
    )
    expect(
      screen.getByTitle(
        'Los tiempos de las reglas se aceleran ×24: 1 minuto de regla equivale a 2.5 segundos reales.',
      ),
    ).toHaveTextContent('MODO DEMO ×24 · 1 min de regla = 2.5 s reales')

    rerender(<Header actualizadoEn={null} escalaTiempo={60} {...sesion} />)
    expect(
      screen.getByTitle(
        'Los tiempos de las reglas se aceleran ×60: 1 minuto de regla equivale a 1 segundo real.',
      ),
    ).toHaveTextContent('MODO DEMO ×60 · 1 min de regla = 1 s real')

    rerender(<Header actualizadoEn={null} escalaTiempo={2} {...sesion} />)
    expect(
      screen.getByTitle(
        'Los tiempos de las reglas se aceleran ×2: 1 minuto de regla equivale a 30 segundos reales.',
      ),
    ).toHaveTextContent('MODO DEMO ×2 · 1 min de regla = 30 s reales')

    rerender(<Header actualizadoEn={null} escalaTiempo={3600} {...sesion} />)
    expect(
      screen.getByTitle(
        'Los tiempos de las reglas se aceleran ×3600: 1 minuto de regla equivale a 17 milisegundos reales.',
      ),
    ).toHaveTextContent('MODO DEMO ×3600 · 1 min de regla = 17 ms reales')
  })

  it('mantiene una escala válida menor que 1', () => {
    render(<Header actualizadoEn={null} escalaTiempo={0.5} {...sesion} />)

    expect(
      screen.getByTitle(
        'Los tiempos de las reglas se aceleran ×0.5: 1 minuto de regla equivale a 120 segundos reales.',
      ),
    ).toHaveTextContent('MODO DEMO ×0.5 · 1 min de regla = 120 s reales')
  })

  it.each([0, -5, Number.NaN, Number.POSITIVE_INFINITY])(
    'no muestra la pill para una escala inválida (%s)',
    (escala) => {
      render(<Header actualizadoEn={null} escalaTiempo={escala} {...sesion} />)

      expect(screen.queryByText(/MODO DEMO/)).not.toBeInTheDocument()
    },
  )

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

  it('muestra Configuración al dueño y la abre al hacer clic', () => {
    const onAbrirConfiguracion = vi.fn()
    render(
      <Header
        actualizadoEn={null}
        usuario="duena"
        rol="dueno"
        onLogout={() => {}}
        onAbrirConfiguracion={onAbrirConfiguracion}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Configuración' }))

    expect(onAbrirConfiguracion).toHaveBeenCalledTimes(1)
  })

  it.each(['jefe_cocina', 'gerente'] as const)(
    'no muestra Configuración a un %s',
    (rol) => {
      render(
        <Header
          actualizadoEn={null}
          usuario="persona"
          rol={rol}
          onLogout={() => {}}
          onAbrirConfiguracion={() => {}}
        />,
      )

      expect(
        screen.queryByRole('button', { name: 'Configuración' }),
      ).not.toBeInTheDocument()
    },
  )
})
