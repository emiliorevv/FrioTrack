import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useReloj } from './useReloj'

function Reloj({ nombre }: { nombre: string }) {
  const ahora = useReloj()
  return <span data-testid={nombre}>{ahora.toISOString()}</span>
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('useReloj', () => {
  it('comparte un solo intervalo y un mismo ahora entre consumidores', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-14T12:00:00Z'))
    const intervalo = vi.spyOn(window, 'setInterval')

    render(
      <>
        <Reloj nombre="reloj-a" />
        <Reloj nombre="reloj-b" />
      </>,
    )

    expect(intervalo).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('reloj-a')).toHaveTextContent(
      '2026-11-14T12:00:00.000Z',
    )
    expect(screen.getByTestId('reloj-b').textContent).toBe(
      screen.getByTestId('reloj-a').textContent,
    )

    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(screen.getByTestId('reloj-a')).toHaveTextContent(
      '2026-11-14T12:00:01.000Z',
    )
    expect(screen.getByTestId('reloj-b').textContent).toBe(
      screen.getByTestId('reloj-a').textContent,
    )
  })
})
