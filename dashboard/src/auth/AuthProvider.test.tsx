import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ErrorApi, iniciarSesion, registrar } from '../api/client'
import { AuthProvider, useAuth } from './AuthProvider'
import {
  getToken,
  leerTokenGuardado,
  notificarNoAutorizado,
  setToken,
} from './token'

vi.mock('../api/client', () => {
  class ErrorApi extends Error {
    readonly status: number
    readonly retryAfterSegundos: number | null
    readonly detalle: string | null

    constructor(
      mensaje: string,
      status: number,
      retryAfterSegundos: number | null = null,
      detalle: string | null = null,
    ) {
      super(mensaje)
      this.name = 'ErrorApi'
      this.status = status
      this.retryAfterSegundos = retryAfterSegundos
      this.detalle = detalle
    }
  }

  return { ErrorApi, iniciarSesion: vi.fn(), registrar: vi.fn() }
})

function crearToken(payload: Record<string, unknown>): string {
  const codificado = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `cabecera.${codificado}.firma`
}

function tokenVigente(
  usuario = 'jefe',
  rol = 'jefe_cocina',
  restauranteId = 1,
): string {
  return crearToken({
    sub: usuario,
    uid: 1,
    rol,
    restaurante_id: restauranteId,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 3600,
    pwd: 'hash',
  })
}

function tokenQueExpiraEn(segundos: number): string {
  return crearToken({
    sub: 'jefe',
    uid: 1,
    rol: 'jefe_cocina',
    restaurante_id: 1,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + segundos,
    pwd: 'hash',
  })
}

function montar() {
  return renderHook(() => useAuth(), { wrapper: AuthProvider })
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  setToken(null)
})

afterEach(() => {
  setToken(null)
  sessionStorage.clear()
  vi.useRealTimers()
})

describe('AuthProvider', () => {
  it('inicia sesión, guarda el JWT y expone usuario y rol', async () => {
    const token = tokenVigente()
    vi.mocked(iniciarSesion).mockResolvedValueOnce({
      access_token: token,
      token_type: 'bearer',
      expira_en_segundos: 28800,
    })

    const { result } = montar()

    let exito!: boolean
    await act(async () => {
      exito = await result.current.login('jefe', 'friotrack-demo')
    })

    expect(exito).toBe(true)
    expect(result.current.token).toBe(token)
    expect(result.current.usuario).toBe('jefe')
    expect(result.current.rol).toBe('jefe_cocina')
    expect(result.current.restauranteId).toBe(1)
    expect(result.current.esDemo).toBe(true)
    expect(result.current.error).toBeNull()
    expect(result.current.cargando).toBe(false)
    expect(getToken()).toBe(token)
    expect(leerTokenGuardado()).toBe(token)
  })

  it('muestra el error de credenciales en un 401', async () => {
    vi.mocked(iniciarSesion).mockRejectedValueOnce(
      new ErrorApi('Usuario o contraseña incorrectos.', 401),
    )

    const { result } = montar()

    let exito!: boolean
    await act(async () => {
      exito = await result.current.login('jefe', 'mala')
    })

    expect(exito).toBe(false)
    expect(result.current.error).toBe('Usuario o contraseña incorrectos.')
    expect(result.current.token).toBeNull()
    expect(getToken()).toBeNull()
  })

  it('usa el mensaje amigable de rate limit y Retry-After en un 429', async () => {
    vi.mocked(iniciarSesion).mockRejectedValueOnce(
      new ErrorApi('La API respondió 429 Too Many Requests', 429, 120),
    )

    const { result } = montar()

    await act(async () => {
      await result.current.login('jefe', 'mala')
    })

    expect(result.current.error).toBe(
      'Demasiados intentos de inicio de sesión. Intenta de nuevo en 120 s.',
    )
    expect(result.current.token).toBeNull()
  })

  it('no muestra “0 s” cuando el 429 trae Retry-After 0', async () => {
    vi.mocked(iniciarSesion).mockRejectedValueOnce(
      new ErrorApi('Too Many Requests', 429, 0),
    )

    const { result } = montar()

    await act(async () => {
      await result.current.login('jefe', 'mala')
    })

    expect(result.current.error).toBe(
      'Demasiados intentos de inicio de sesión. Intenta de nuevo más tarde.',
    )
    expect(result.current.error).not.toContain('0 s')
  })

  it('usa el detalle real de un 500 y cae al genérico sin detalle', async () => {
    vi.mocked(iniciarSesion).mockRejectedValueOnce(
      new ErrorApi('La API respondió 500 Internal Server Error', 500),
    )

    const { result } = montar()

    await act(async () => {
      await result.current.login('jefe', 'mala')
    })
    expect(result.current.error).toBe('No se pudo iniciar sesión.')

    vi.mocked(iniciarSesion).mockRejectedValueOnce(
      new ErrorApi('Base de datos caída', 500, null, 'Base de datos caída'),
    )

    await act(async () => {
      await result.current.login('jefe', 'mala')
    })
    expect(result.current.error).toBe('Base de datos caída')
  })

  it('restaura una sesión válida sin volver a pedir login', () => {
    const token = tokenVigente('gerente', 'gerente')
    setToken(token)

    const { result } = montar()

    expect(result.current.token).toBe(token)
    expect(result.current.usuario).toBe('gerente')
    expect(result.current.rol).toBe('gerente')
    expect(result.current.restauranteId).toBe(1)
    expect(result.current.esDemo).toBe(true)
    expect(iniciarSesion).not.toHaveBeenCalled()
  })

  it('marca esDemo=false para un tenant que no es el demo', () => {
    setToken(tokenVigente('jefe-otro', 'jefe_cocina', 2))

    const { result } = montar()

    expect(result.current.restauranteId).toBe(2)
    expect(result.current.esDemo).toBe(false)
  })

  it('limpia un token expirado al restaurar', () => {
    setToken(
      crearToken({
        sub: 'jefe',
        rol: 'jefe_cocina',
        restaurante_id: 1,
        exp: Math.floor(Date.now() / 1000) - 10,
      }),
    )

    const { result } = montar()

    expect(result.current.token).toBeNull()
    expect(getToken()).toBeNull()
    expect(leerTokenGuardado()).toBeNull()
  })

  it('limpia un token mal formado al restaurar', () => {
    setToken('no-es-un-jwt')

    const { result } = montar()

    expect(result.current.token).toBeNull()
    expect(getToken()).toBeNull()
  })

  it('logout limpia el estado y el almacenamiento', () => {
    setToken(tokenVigente())
    const { result } = montar()
    expect(result.current.token).not.toBeNull()

    act(() => {
      result.current.logout()
    })

    expect(result.current.token).toBeNull()
    expect(result.current.usuario).toBeNull()
    expect(result.current.rol).toBeNull()
    expect(getToken()).toBeNull()
    expect(leerTokenGuardado()).toBeNull()
  })

  it('cierra la sesión cuando vence el exp del JWT', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-15T10:00:00Z'))
    const token = tokenQueExpiraEn(60)
    setToken(token)

    const { result } = montar()
    expect(result.current.token).toBe(token)

    act(() => {
      vi.advanceTimersByTime(60_000)
    })

    expect(result.current.token).toBeNull()
    expect(result.current.error).toBe(
      'Tu sesión expiró. Inicia sesión de nuevo.',
    )
    expect(getToken()).toBeNull()
  })

  it('logout cancela el temporizador de expiración', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-15T10:00:00Z'))
    setToken(tokenQueExpiraEn(60))

    const { result } = montar()
    act(() => {
      result.current.logout()
    })
    act(() => {
      vi.advanceTimersByTime(120_000)
    })

    expect(result.current.token).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('un login nuevo reemplaza el temporizador anterior', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-15T10:00:00Z'))
    setToken(tokenQueExpiraEn(60))

    const { result } = montar()
    const nuevoToken = tokenQueExpiraEn(3600)
    vi.mocked(iniciarSesion).mockResolvedValueOnce({
      access_token: nuevoToken,
      token_type: 'bearer',
      expira_en_segundos: 3600,
    })

    await act(async () => {
      await result.current.login('jefe', 'friotrack-demo')
    })

    act(() => {
      vi.advanceTimersByTime(60_000)
    })

    expect(result.current.token).toBe(nuevoToken)
    expect(result.current.error).toBeNull()
  })

  it('un 401 global cierra la sesión y explica que expiró', () => {
    setToken(tokenVigente())
    const { result } = montar()
    expect(result.current.token).not.toBeNull()

    act(() => {
      notificarNoAutorizado()
    })

    expect(result.current.token).toBeNull()
    expect(result.current.error).toBe(
      'Tu sesión expiró. Inicia sesión de nuevo.',
    )
    expect(getToken()).toBeNull()
  })

  it('mantiene cargando mientras responde el login', async () => {
    let resolver!: (respuesta: {
      access_token: string
      token_type: string
      expira_en_segundos: number
    }) => void
    const pendiente = new Promise<{
      access_token: string
      token_type: string
      expira_en_segundos: number
    }>((resolve) => {
      resolver = resolve
    })
    vi.mocked(iniciarSesion).mockReturnValueOnce(pendiente)

    const { result } = montar()
    let promesa!: Promise<boolean>
    act(() => {
      promesa = result.current.login('jefe', 'friotrack-demo')
    })

    await waitFor(() => expect(result.current.cargando).toBe(true))

    await act(async () => {
      resolver({
        access_token: tokenVigente(),
        token_type: 'bearer',
        expira_en_segundos: 28800,
      })
      await promesa
    })

    expect(result.current.cargando).toBe(false)
  })
})

describe('AuthProvider · registro', () => {
  it('registra, guarda el JWT y expone al dueño', async () => {
    const token = tokenVigente('dueno-nuevo', 'dueno')
    vi.mocked(registrar).mockResolvedValueOnce({
      access_token: token,
      token_type: 'bearer',
      expira_en_segundos: 28800,
    })

    const { result } = montar()

    let exito!: boolean
    await act(async () => {
      exito = await result.current.registro(
        'Taquería del Norte',
        'dueno-nuevo',
        'friotrack-demo',
      )
    })

    expect(registrar).toHaveBeenCalledWith(
      'Taquería del Norte',
      'dueno-nuevo',
      'friotrack-demo',
    )
    expect(exito).toBe(true)
    expect(result.current.token).toBe(token)
    expect(result.current.usuario).toBe('dueno-nuevo')
    expect(result.current.rol).toBe('dueno')
    expect(result.current.error).toBeNull()
    expect(result.current.cargando).toBe(false)
    expect(getToken()).toBe(token)
    expect(leerTokenGuardado()).toBe(token)
  })

  it('un 409 no guarda token y explica el fallo sin detalles técnicos', async () => {
    vi.mocked(registrar).mockRejectedValueOnce(
      new ErrorApi('No se pudo completar el registro.', 409),
    )

    const { result } = montar()

    let exito!: boolean
    await act(async () => {
      exito = await result.current.registro(
        'Taquería del Norte',
        'dueno-nuevo',
        'friotrack-demo',
      )
    })

    expect(exito).toBe(false)
    expect(result.current.error).toBe(
      'No se pudo completar el registro. Revisa los datos o prueba con otro usuario.',
    )
    expect(result.current.token).toBeNull()
    expect(getToken()).toBeNull()
    expect(leerTokenGuardado()).toBeNull()
  })

  it('traduce un 422 con los límites compartidos', async () => {
    vi.mocked(registrar).mockRejectedValueOnce(
      new ErrorApi('Unprocessable Entity', 422),
    )

    const { result } = montar()

    await act(async () => {
      await result.current.registro('Taquería', 'ab', 'corta')
    })

    expect(result.current.error).toBe(
      'Revisa los datos: restaurante 2-120 caracteres, usuario 3-64 y contraseña 8-128.',
    )
    expect(getToken()).toBeNull()
  })

  it('usa el mensaje de rate limit y Retry-After en un 429', async () => {
    vi.mocked(registrar).mockRejectedValueOnce(
      new ErrorApi('Too Many Requests', 429, 30),
    )

    const { result } = montar()

    await act(async () => {
      await result.current.registro('Taquería', 'dueno-nuevo', 'friotrack-demo')
    })

    expect(result.current.error).toBe(
      'Demasiados registros desde esta red. Intenta de nuevo en 30 s.',
    )
    expect(getToken()).toBeNull()
  })

  it('no muestra “0 s” cuando el 429 de registro trae Retry-After 0', async () => {
    vi.mocked(registrar).mockRejectedValueOnce(
      new ErrorApi('Too Many Requests', 429, 0),
    )

    const { result } = montar()

    await act(async () => {
      await result.current.registro('Taquería', 'dueno-nuevo', 'friotrack-demo')
    })

    expect(result.current.error).toBe(
      'Demasiados registros desde esta red. Intenta de nuevo más tarde.',
    )
    expect(result.current.error).not.toContain('0 s')
  })

  it('avisa que la cuenta existe si el JWT del 201 no es válido', async () => {
    vi.mocked(registrar).mockResolvedValueOnce({
      access_token: 'no-es-un-jwt',
      token_type: 'bearer',
      expira_en_segundos: 28800,
    })

    const { result } = montar()

    let exito!: boolean
    await act(async () => {
      exito = await result.current.registro(
        'Taquería del Norte',
        'dueno-nuevo',
        'friotrack-demo',
      )
    })

    expect(exito).toBe(false)
    expect(result.current.error).toBe(
      'Tu cuenta se creó, pero no pudimos iniciar la sesión. Inicia sesión con tus credenciales.',
    )
    expect(result.current.token).toBeNull()
    expect(getToken()).toBeNull()
    expect(leerTokenGuardado()).toBeNull()
  })

  it('cae a un mensaje accionable cuando falla la red', async () => {
    vi.mocked(registrar).mockRejectedValueOnce(new TypeError('Failed to fetch'))

    const { result } = montar()

    await act(async () => {
      await result.current.registro('Taquería', 'dueno-nuevo', 'friotrack-demo')
    })

    expect(result.current.error).toBe(
      'No se pudo crear la cuenta. Revisa tu conexión e intenta de nuevo.',
    )
    expect(getToken()).toBeNull()
  })

  it('programa la expiración de la sesión recién registrada', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-15T10:00:00Z'))
    const token = tokenQueExpiraEn(60)
    vi.mocked(registrar).mockResolvedValueOnce({
      access_token: token,
      token_type: 'bearer',
      expira_en_segundos: 60,
    })

    const { result } = montar()

    await act(async () => {
      await result.current.registro('Taquería', 'dueno-nuevo', 'friotrack-demo')
    })
    expect(result.current.token).toBe(token)

    act(() => {
      vi.advanceTimersByTime(60_000)
    })

    expect(result.current.token).toBeNull()
    expect(result.current.error).toBe(
      'Tu sesión expiró. Inicia sesión de nuevo.',
    )
    expect(getToken()).toBeNull()
  })

  it('limpiarError borra el error al cambiar de formulario', async () => {
    vi.mocked(registrar).mockRejectedValueOnce(
      new ErrorApi('Too Many Requests', 429, 30),
    )

    const { result } = montar()

    await act(async () => {
      await result.current.registro('Taquería', 'dueno-nuevo', 'friotrack-demo')
    })
    expect(result.current.error).not.toBeNull()

    act(() => {
      result.current.limpiarError()
    })

    expect(result.current.error).toBeNull()
  })
})
