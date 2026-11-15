import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ErrorApi, iniciarSesion } from '../api/client'
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

  return { ErrorApi, iniciarSesion: vi.fn() }
})

function crearToken(payload: Record<string, unknown>): string {
  const codificado = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `cabecera.${codificado}.firma`
}

function tokenVigente(usuario = 'jefe', rol = 'jefe_cocina'): string {
  return crearToken({
    sub: usuario,
    uid: 1,
    rol,
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
    expect(iniciarSesion).not.toHaveBeenCalled()
  })

  it('limpia un token expirado al restaurar', () => {
    setToken(
      crearToken({
        sub: 'jefe',
        rol: 'jefe_cocina',
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
