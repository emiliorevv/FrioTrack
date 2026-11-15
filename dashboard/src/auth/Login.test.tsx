import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Login } from './Login'

const auth = vi.hoisted(() => ({
  login: vi.fn(),
  cargando: false,
  error: null as string | null,
}))

vi.mock('./AuthProvider', () => ({
  useAuth: () => auth,
}))

beforeEach(() => {
  auth.login.mockReset()
  auth.cargando = false
  auth.error = null
})

describe('Login', () => {
  it('muestra la marca, los campos y la pista de demo', () => {
    render(<Login />)

    expect(
      screen.getByRole('heading', { name: 'Iniciar sesión' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Monitoreo de cadena de frío')).toBeInTheDocument()
    expect(screen.getByLabelText('Usuario')).toHaveAttribute(
      'autocomplete',
      'username',
    )
    expect(screen.getByLabelText('Contraseña')).toHaveAttribute(
      'autocomplete',
      'current-password',
    )
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeEnabled()
    expect(screen.getByText('Demo: jefe / friotrack-demo')).toBeInTheDocument()
  })

  it('envía usuario y contraseña al login', async () => {
    auth.login.mockResolvedValueOnce(true)
    render(<Login />)

    fireEvent.change(screen.getByLabelText('Usuario'), {
      target: { value: 'jefe' },
    })
    fireEvent.change(screen.getByLabelText('Contraseña'), {
      target: { value: 'friotrack-demo' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => {
      expect(auth.login).toHaveBeenCalledWith('jefe', 'friotrack-demo')
    })
  })

  it('muestra el error del provider con role alert', () => {
    auth.error = 'Usuario o contraseña incorrectos'
    render(<Login />)

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Usuario o contraseña incorrectos',
    )
  })

  it('deshabilita el formulario y muestra “Entrando…” durante el login', () => {
    auth.cargando = true
    render(<Login />)

    expect(screen.getByLabelText('Usuario')).toBeDisabled()
    expect(screen.getByLabelText('Contraseña')).toBeDisabled()
    const boton = screen.getByRole('button', { name: 'Entrando…' })
    expect(boton).toBeDisabled()
    expect(boton).toHaveAttribute('aria-busy', 'true')
  })
})
