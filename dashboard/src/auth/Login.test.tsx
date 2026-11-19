import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ErrorApi, iniciarSesion, registrar } from '../api/client'
import { AuthProvider } from './AuthProvider'
import { Login } from './Login'
import { setToken } from './token'

vi.mock('../api/client', async (importOriginal) => {
  const real = await importOriginal<typeof import('../api/client')>()
  return { ...real, iniciarSesion: vi.fn(), registrar: vi.fn() }
})

function crearToken(payload: Record<string, unknown>): string {
  const codificado = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `cabecera.${codificado}.firma`
}

function sesionNueva(usuario = 'dueno-nuevo', rol = 'dueno') {
  return {
    access_token: crearToken({
      sub: usuario,
      uid: 7,
      rol,
      restaurante_id: 1,
      es_demo: true,
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor(Date.now() / 1000) + 3600,
      pwd: 'hash',
    }),
    token_type: 'bearer',
    expira_en_segundos: 28800,
  }
}

function renderizar() {
  return render(
    <AuthProvider>
      <Login />
    </AuthProvider>,
  )
}

function abrirRegistro() {
  fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
}

function llenarRegistro({
  restaurante = 'Taquería del Norte',
  usuario = 'dueno-nuevo',
  password = 'friotrack-demo',
  confirmacion = 'friotrack-demo',
}: Partial<Record<string, string>> = {}) {
  fireEvent.change(screen.getByLabelText('Restaurante'), {
    target: { value: restaurante },
  })
  fireEvent.change(screen.getByLabelText('Usuario'), {
    target: { value: usuario },
  })
  fireEvent.change(screen.getByLabelText(/^Contraseña$/), {
    target: { value: password },
  })
  fireEvent.change(screen.getByLabelText('Confirmar contraseña'), {
    target: { value: confirmacion },
  })
}

async function enviarRegistro() {
  fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
  await waitFor(() => expect(registrar).toHaveBeenCalled())
}

beforeEach(() => {
  vi.clearAllMocks()
  setToken(null)
  sessionStorage.clear()
})

describe('Login', () => {
  it('muestra la marca, los campos y la pista de demo', () => {
    renderizar()

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
    expect(
      screen.getByText('Demo: jefe / dueno / gerente · friotrack-demo'),
    ).toBeInTheDocument()
  })

  it('envía usuario y contraseña al login', async () => {
    vi.mocked(iniciarSesion).mockResolvedValueOnce({
      ...sesionNueva('jefe', 'jefe_cocina'),
      expira_en_segundos: 28800,
    })
    renderizar()

    fireEvent.change(screen.getByLabelText('Usuario'), {
      target: { value: 'jefe' },
    })
    fireEvent.change(screen.getByLabelText('Contraseña'), {
      target: { value: 'friotrack-demo' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => {
      expect(iniciarSesion).toHaveBeenCalledWith('jefe', 'friotrack-demo')
    })
  })

  it('cambia al modo de registro sin recargar y vuelve al login', () => {
    renderizar()

    abrirRegistro()

    expect(
      screen.getByRole('heading', { name: 'Crear cuenta' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Restaurante')).toHaveAttribute(
      'autocomplete',
      'organization',
    )
    expect(screen.getByLabelText('Usuario')).toHaveAttribute(
      'autocomplete',
      'username',
    )
    expect(screen.getByLabelText(/^Contraseña$/)).toHaveAttribute(
      'autocomplete',
      'new-password',
    )
    expect(screen.getByLabelText('Confirmar contraseña')).toHaveAttribute(
      'autocomplete',
      'new-password',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Ya tengo cuenta' }))

    expect(
      screen.getByRole('heading', { name: 'Iniciar sesión' }),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Restaurante')).not.toBeInTheDocument()
  })

  it('valida restaurante, usuario, contraseña y confirmación en el cliente', () => {
    renderizar()
    abrirRegistro()

    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Escribe el nombre de tu restaurante.',
    )

    fireEvent.change(screen.getByLabelText('Restaurante'), {
      target: { value: 'A' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'El restaurante debe tener entre 2 y 120 caracteres.',
    )

    fireEvent.change(screen.getByLabelText('Restaurante'), {
      target: { value: '  Taquería del Norte  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Escribe un usuario.')

    fireEvent.change(screen.getByLabelText('Usuario'), {
      target: { value: 'ab' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'El usuario debe tener entre 3 y 64 caracteres.',
    )

    fireEvent.change(screen.getByLabelText('Usuario'), {
      target: { value: 'dueno-nuevo' },
    })
    fireEvent.change(screen.getByLabelText(/^Contraseña$/), {
      target: { value: 'corta' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'La contraseña debe tener entre 8 y 128 caracteres.',
    )

    fireEvent.change(screen.getByLabelText(/^Contraseña$/), {
      target: { value: 'friotrack-demo' },
    })
    fireEvent.change(screen.getByLabelText('Confirmar contraseña'), {
      target: { value: 'otra-clave' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Las contraseñas no coinciden.',
    )

    expect(registrar).not.toHaveBeenCalled()
  })

  it('rechaza los máximos de restaurante, usuario y contraseña', () => {
    renderizar()
    abrirRegistro()

    llenarRegistro({ restaurante: 'R'.repeat(121) })
    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'El restaurante debe tener entre 2 y 120 caracteres.',
    )

    llenarRegistro({ usuario: 'u'.repeat(65) })
    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'El usuario debe tener entre 3 y 64 caracteres.',
    )

    llenarRegistro({
      password: 'p'.repeat(129),
      confirmacion: 'p'.repeat(129),
    })
    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'La contraseña debe tener entre 8 y 128 caracteres.',
    )

    expect(registrar).not.toHaveBeenCalled()
  })

  it('cuenta code points: cuatro emojis no llegan al mínimo de 8', () => {
    renderizar()
    abrirRegistro()
    llenarRegistro({
      password: '😀😀😀😀',
      confirmacion: '😀😀😀😀',
    })

    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))

    expect(screen.getByRole('alert')).toHaveTextContent(
      'La contraseña debe tener entre 8 y 128 caracteres.',
    )
    expect(registrar).not.toHaveBeenCalled()
  })

  it('valida los máximos del login antes de llamar a la API', () => {
    renderizar()

    fireEvent.change(screen.getByLabelText('Usuario'), {
      target: { value: 'u'.repeat(65) },
    })
    fireEvent.change(screen.getByLabelText('Contraseña'), {
      target: { value: 'friotrack-demo' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'El usuario no puede superar los 64 caracteres.',
    )

    fireEvent.change(screen.getByLabelText('Usuario'), {
      target: { value: 'jefe' },
    })
    fireEvent.change(screen.getByLabelText('Contraseña'), {
      target: { value: 'p'.repeat(129) },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'La contraseña no puede superar los 128 caracteres.',
    )

    expect(iniciarSesion).not.toHaveBeenCalled()
  })

  it('envía el registro con los campos recortados y guarda la sesión', async () => {
    vi.mocked(registrar).mockResolvedValueOnce(sesionNueva())
    renderizar()
    abrirRegistro()

    llenarRegistro({
      restaurante: '  Taquería del Norte  ',
      usuario: '  dueno-nuevo  ',
    })
    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))

    await waitFor(() => {
      expect(registrar).toHaveBeenCalledWith(
        'Taquería del Norte',
        'dueno-nuevo',
        'friotrack-demo',
      )
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(sessionStorage.getItem('friotrack.token')).not.toBeNull()
  })

  it('muestra el mensaje amigable de un 409 sin detalles técnicos', async () => {
    vi.mocked(registrar).mockRejectedValueOnce(
      new ErrorApi('No se pudo completar el registro.', 409),
    )
    renderizar()
    abrirRegistro()
    llenarRegistro()

    await enviarRegistro()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'No se pudo completar el registro. Revisa los datos o prueba con otro usuario.',
    )
  })

  it('muestra el mensaje de validación del backend en un 422', async () => {
    vi.mocked(registrar).mockRejectedValueOnce(
      new ErrorApi('Unprocessable Entity', 422),
    )
    renderizar()
    abrirRegistro()
    llenarRegistro()

    await enviarRegistro()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Revisa los datos: restaurante 2-120 caracteres, usuario 3-64 y contraseña 8-128.',
    )
  })

  it('muestra el rate limit del registro con Retry-After en un 429', async () => {
    vi.mocked(registrar).mockRejectedValueOnce(
      new ErrorApi('Too Many Requests', 429, 45),
    )
    renderizar()
    abrirRegistro()
    llenarRegistro()

    await enviarRegistro()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Demasiados registros desde esta red. Intenta de nuevo en 45 s.',
    )
  })

  it('no promete un reintento inmediato si Retry-After es 0', async () => {
    vi.mocked(registrar).mockRejectedValueOnce(
      new ErrorApi('Too Many Requests', 429, 0),
    )
    renderizar()
    abrirRegistro()
    llenarRegistro()

    await enviarRegistro()

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent(
      'Demasiados registros desde esta red. Intenta de nuevo más tarde.',
    )
    expect(alerta).not.toHaveTextContent('0 s')
  })

  it('avisa que la cuenta se creó si el JWT del 201 no es utilizable', async () => {
    vi.mocked(registrar).mockResolvedValueOnce({
      access_token: 'no-es-un-jwt',
      token_type: 'bearer',
      expira_en_segundos: 28800,
    })
    renderizar()
    abrirRegistro()
    llenarRegistro()

    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Tu cuenta se creó, pero no pudimos iniciar la sesión. Inicia sesión con tus credenciales.',
    )
    expect(screen.getByLabelText('Restaurante')).toHaveValue(
      'Taquería del Norte',
    )
    expect(screen.getByLabelText('Usuario')).toHaveValue('dueno-nuevo')
    expect(sessionStorage.getItem('friotrack.token')).toBeNull()
  })

  it('usa los textos de botón de login sin ternarios anidados', async () => {
    vi.mocked(iniciarSesion).mockReturnValueOnce(new Promise<never>(() => {}))
    renderizar()

    expect(screen.getByRole('button', { name: 'Entrar' })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Usuario'), {
      target: { value: 'jefe' },
    })
    fireEvent.change(screen.getByLabelText('Contraseña'), {
      target: { value: 'friotrack-demo' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(
      await screen.findByRole('button', { name: 'Entrando…' }),
    ).toBeDisabled()
  })

  it('no expone la contraseña en el texto visible', () => {
    renderizar()
    abrirRegistro()
    llenarRegistro({ password: 'secreta-123', confirmacion: 'secreta-123' })

    expect(screen.getByLabelText(/^Contraseña$/)).toHaveAttribute(
      'type',
      'password',
    )
    expect(screen.getByLabelText('Confirmar contraseña')).toHaveAttribute(
      'type',
      'password',
    )
    expect(screen.queryByText('secreta-123')).not.toBeInTheDocument()
  })

  it('deshabilita el formulario y muestra “Creando cuenta…” mientras registra', async () => {
    vi.mocked(registrar).mockReturnValueOnce(new Promise<never>(() => {}))
    renderizar()
    abrirRegistro()
    llenarRegistro()

    fireEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))

    const boton = await screen.findByRole('button', {
      name: 'Creando cuenta…',
    })
    expect(boton).toBeDisabled()
    expect(boton).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByLabelText('Restaurante')).toBeDisabled()
    expect(screen.getByLabelText('Confirmar contraseña')).toBeDisabled()
  })
})
