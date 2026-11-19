import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ErrorApi,
  recuperarDemo,
  simularAtaque,
  simularFalla,
  simularPuerta,
} from '../api/client'
import { PanelDemo } from './PanelDemo'

vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>()
  return {
    ...original,
    simularFalla: vi.fn(),
    simularPuerta: vi.fn(),
    simularAtaque: vi.fn(),
    recuperarDemo: vi.fn(),
  }
})

const onCerrar = vi.fn()
const onCambio = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(simularFalla).mockResolvedValue(undefined)
  vi.mocked(simularPuerta).mockResolvedValue(undefined)
  vi.mocked(simularAtaque).mockResolvedValue(undefined)
  vi.mocked(recuperarDemo).mockResolvedValue(undefined)
})

afterEach(() => {
  vi.useRealTimers()
})

function renderizar() {
  return render(<PanelDemo onCerrar={onCerrar} onCambio={onCambio} />)
}

async function clickAccion(nombre: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: nombre }))
  })
}

describe('PanelDemo', () => {
  it('muestra las cuatro acciones', () => {
    renderizar()

    expect(
      screen.getByRole('dialog', { name: 'Panel de demo' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Simular falla de compresor' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Simular puerta abierta' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Simular ataque SIEM' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Recuperar cámaras' }),
    ).toBeInTheDocument()
  })

  it('simula la falla sin cámara explícita y refresca a los 2 s y 30 s', async () => {
    vi.useFakeTimers()
    renderizar()

    await clickAccion('Simular falla de compresor')

    expect(simularFalla).toHaveBeenCalledWith()
    expect(onCambio).not.toHaveBeenCalled()
    expect(
      screen.getByText('Simulación iniciada; observa las cámaras.'),
    ).toBeInTheDocument()

    await act(async () => {
      vi.advanceTimersByTime(1_999)
    })
    expect(onCambio).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(onCambio).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.advanceTimersByTime(28_000)
    })
    expect(onCambio).toHaveBeenCalledTimes(2)
  })

  it('simula la puerta sin cámara explícita', async () => {
    renderizar()

    await clickAccion('Simular puerta abierta')

    expect(simularPuerta).toHaveBeenCalledWith()
    expect(
      screen.getByText('Simulación iniciada; observa la alerta de puerta.'),
    ).toBeInTheDocument()
  })

  it('refresca el ataque a los 500 ms', async () => {
    vi.useFakeTimers()
    renderizar()

    await clickAccion('Simular ataque SIEM')
    expect(simularAtaque).toHaveBeenCalledWith()

    await act(async () => {
      vi.advanceTimersByTime(499)
    })
    expect(onCambio).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(onCambio).toHaveBeenCalledTimes(1)
  })

  it('refresca la recuperación a los 2 s', async () => {
    vi.useFakeTimers()
    renderizar()

    await clickAccion('Recuperar cámaras')
    expect(recuperarDemo).toHaveBeenCalledWith()
    expect(onCambio).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(2_000)
    })
    expect(onCambio).toHaveBeenCalledTimes(1)
  })

  it('limpia los timers al desmontar', async () => {
    vi.useFakeTimers()
    const { unmount } = renderizar()

    await clickAccion('Simular falla de compresor')
    unmount()

    await act(async () => {
      vi.advanceTimersByTime(30_000)
    })
    expect(onCambio).not.toHaveBeenCalled()
  })

  it('bloquea los botones mientras hay una simulación en vuelo', async () => {
    let resolver!: () => void
    vi.mocked(simularFalla).mockReturnValue(
      new Promise<void>((resolve) => {
        resolver = resolve
      }),
    )
    renderizar()

    fireEvent.click(
      screen.getByRole('button', { name: 'Simular falla de compresor' }),
    )

    const enCurso = await screen.findByRole('button', {
      name: 'Simulando…',
    })
    expect(enCurso).toHaveAttribute('aria-busy', 'true')
    expect(
      screen.getByRole('button', { name: 'Simular puerta abierta' }),
    ).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Cerrar panel de demo' }),
    ).toBeDisabled()

    resolver()

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Simular falla de compresor' }),
      ).toBeEnabled(),
    )
  })

  it('explica un 404 cuando la simulación no está disponible', async () => {
    vi.mocked(simularFalla).mockRejectedValue(new ErrorApi('Not Found', 404))
    renderizar()

    await clickAccion('Simular falla de compresor')

    expect(
      screen.getByText('La simulación no está disponible en este entorno.'),
    ).toBeInTheDocument()
    expect(onCambio).not.toHaveBeenCalled()
  })

  it('explica un 403 de rol', async () => {
    vi.mocked(simularFalla).mockRejectedValue(new ErrorApi('Prohibido', 403))
    renderizar()

    await clickAccion('Simular falla de compresor')

    expect(
      screen.getByText('Tu rol no permite usar la simulación.'),
    ).toBeInTheDocument()
  })

  it('muestra el detalle de un 409 de simulación repetida', async () => {
    const detalle = 'Ya hay una simulación de falla en curso.'
    vi.mocked(simularFalla).mockRejectedValue(
      new ErrorApi(detalle, 409, null, detalle),
    )
    renderizar()

    await clickAccion('Simular falla de compresor')

    expect(screen.getByText(detalle)).toBeInTheDocument()
    expect(onCambio).not.toHaveBeenCalled()
  })

  it('cierra desde el botón del diálogo', () => {
    renderizar()

    fireEvent.click(
      within(screen.getByRole('dialog', { name: 'Panel de demo' })).getByRole(
        'button',
        { name: 'Cerrar panel de demo' },
      ),
    )

    expect(onCerrar).toHaveBeenCalledTimes(1)
  })
})
