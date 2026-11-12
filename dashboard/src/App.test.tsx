import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import App from './App'

beforeEach(() => {
  window.localStorage.clear()
})

describe('vista general', () => {
  it('muestra los KPIs principales y las cinco cámaras', () => {
    render(<App />)

    expect(screen.getAllByRole('article')).toHaveLength(5)
    expect(screen.getByText('97.3%')).toBeInTheDocument()
    expect(screen.getByText('6.5 min')).toBeInTheDocument()
    expect(screen.getByText('Alertas activas')).toBeInTheDocument()
    expect(screen.getByText('Valor en riesgo')).toBeInTheDocument()
    expect(screen.getByText('$1,720')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', {
        level: 3,
        name: 'Pescados y mariscos',
      }),
    ).toBeInTheDocument()
  })

  it('muestra la etiqueta de modo demo', () => {
    render(<App />)

    expect(screen.getByText('MODO DEMO ×30')).toBeInTheDocument()
  })

  it('el filtro Alerta deja solo Pescados y mariscos', () => {
    render(<App />)

    const chipAlerta = screen.getByRole('button', { name: 'Alerta (1)' })
    expect(chipAlerta).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(chipAlerta)

    expect(chipAlerta).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(
      screen.getByRole('article', { name: 'Pescados y mariscos' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('article', { name: 'Carnes y aves' }),
    ).not.toBeInTheDocument()
  })

  it('la búsqueda congelador deja solo el Congelador', () => {
    render(<App />)

    fireEvent.change(screen.getByLabelText('Buscar cámara'), {
      target: { value: 'congelador' },
    })

    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(
      screen.getByRole('article', { name: 'Congelador' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('article', { name: 'Pescados y mariscos' }),
    ).not.toBeInTheDocument()
  })

  it('el banner de onboarding se puede cerrar', () => {
    render(<App />)

    expect(
      screen.getByText(
        'FríoTrack vigila tus cámaras. Si algo sale de rango, te avisa por SMS.',
      ),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar aviso' }))

    expect(
      screen.queryByText(/FríoTrack vigila tus cámaras/),
    ).not.toBeInTheDocument()
  })

  it('el estado de alerta se anuncia en texto, no solo con color', () => {
    render(<App />)

    const pescados = screen.getByRole('article', {
      name: 'Pescados y mariscos',
    })

    expect(within(pescados).getByText('Alerta')).toBeInTheDocument()
    expect(within(pescados).getByText('Abierta')).toBeInTheDocument()
    expect(within(pescados).getByText('$4,850')).toBeInTheDocument()
  })
})
