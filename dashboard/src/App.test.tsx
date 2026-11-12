import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('muestra el nombre de la app y el panel de monitoreo', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { name: 'FríoTrack' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Panel de monitoreo' }),
    ).toBeInTheDocument()
  })
})
