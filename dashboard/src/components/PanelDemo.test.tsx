import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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
  vi.mocked(simularAtaque).mockResolvedValue(null)
  vi.mocked(recuperarDemo).mockResolvedValue(undefined)
})

function renderizar(props: { esDemo?: boolean; rol?: string } = {}) {
  return render(
    <PanelDemo
      esDemo={props.esDemo ?? true}
      rol={props.rol ?? 'dueno'}
      onCerrar={onCerrar}
      onCambio={onCambio}
    />,
  )
}

describe('PanelDemo', () => {
  it('no se muestra fuera del tenant demo', () => {
    const { container } = renderizar({ esDemo: false, rol: 'dueno' })
    expect(container).toBeEmptyDOMElement()
  })

  it.each(['gerente', 'otro'])('no se muestra para el rol %s', (rol) => {
    const { container } = renderizar({ esDemo: true, rol })
    expect(container).toBeEmptyDOMElement()
  })

  it('muestra las cuatro acciones al dueño del tenant demo', () => {
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

  it('simula la falla, avisa y refresca el dashboard', async () => {
    renderizar()

    fireEvent.click(
      screen.getByRole('button', { name: 'Simular falla de compresor' }),
    )

    await waitFor(() => expect(simularFalla).toHaveBeenCalledWith(1))
    expect(onCambio).toHaveBeenCalledTimes(1)
    expect(
      screen.getByText('Simulación iniciada; observa la cámara de pescados.'),
    ).toBeInTheDocument()
  })

  it('simula la puerta en la cámara 5', async () => {
    renderizar()

    fireEvent.click(
      screen.getByRole('button', { name: 'Simular puerta abierta' }),
    )

    await waitFor(() => expect(simularPuerta).toHaveBeenCalledWith(5))
    expect(onCambio).toHaveBeenCalledTimes(1)
  })

  it('simula el ataque y refresca también seguridad', async () => {
    renderizar()

    fireEvent.click(screen.getByRole('button', { name: 'Simular ataque SIEM' }))

    await waitFor(() => expect(simularAtaque).toHaveBeenCalledTimes(1))
    expect(onCambio).toHaveBeenCalledTimes(1)
    expect(
      screen.getByText('Ataque simulado; revisa el panel de Seguridad.'),
    ).toBeInTheDocument()
  })

  it('recupera las cámaras', async () => {
    renderizar()

    fireEvent.click(screen.getByRole('button', { name: 'Recuperar cámaras' }))

    await waitFor(() => expect(recuperarDemo).toHaveBeenCalledTimes(1))
    expect(
      screen.getByText('Cámaras recuperadas; el dashboard se actualizará.'),
    ).toBeInTheDocument()
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

    fireEvent.click(
      screen.getByRole('button', { name: 'Simular falla de compresor' }),
    )

    expect(
      await screen.findByText(
        'La simulación no está disponible en este entorno.',
      ),
    ).toBeInTheDocument()
    expect(onCambio).not.toHaveBeenCalled()
  })

  it('explica un 403 de rol', async () => {
    vi.mocked(simularFalla).mockRejectedValue(new ErrorApi('Prohibido', 403))
    renderizar()

    fireEvent.click(
      screen.getByRole('button', { name: 'Simular falla de compresor' }),
    )

    expect(
      await screen.findByText('Tu rol no permite usar la simulación.'),
    ).toBeInTheDocument()
  })

  it('muestra el detalle de un 409 de simulación repetida', async () => {
    const detalle = 'Ya hay una simulación en curso.'
    vi.mocked(simularFalla).mockRejectedValue(
      new ErrorApi(detalle, 409, null, detalle),
    )
    renderizar()

    fireEvent.click(
      screen.getByRole('button', { name: 'Simular falla de compresor' }),
    )

    expect(await screen.findByText(detalle)).toBeInTheDocument()
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
