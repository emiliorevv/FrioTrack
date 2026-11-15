import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  atenderAlerta,
  ErrorApi,
  iniciarSesion,
  obtenerAlertasActivas,
  obtenerAlertasSeguridad,
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
  pedir,
} from './client'
import { setToken, suscribirNoAutorizado } from '../auth/token'
import { resolverApiUrl } from './url'

vi.mock('./url', () => ({
  resolverApiUrl: vi.fn(() => 'http://api.prueba.mx/api'),
}))

const BASE = 'http://api.prueba.mx/api'
const fetchFalso = vi.fn()

function respuesta(
  datos: unknown,
  estado = 200,
  texto = 'OK',
  cabeceras: Record<string, string> = {},
): Response {
  return {
    ok: estado >= 200 && estado < 300,
    status: estado,
    statusText: texto,
    headers: new Headers(cabeceras),
    json: async () => datos,
  } as unknown as Response
}

beforeEach(() => {
  setToken(null)
  fetchFalso.mockReset()
  vi.stubGlobal('fetch', fetchFalso)
  vi.mocked(resolverApiUrl).mockReturnValue(BASE)
})

afterEach(() => {
  setToken(null)
  sessionStorage.clear()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('pedir', () => {
  it('pide JSON a la ruta de la base resuelta', async () => {
    const camaras = [
      {
        id: 1,
        nombre: 'Pescados y mariscos',
        rango_min_c: 0,
        rango_max_c: 2,
        min_para_riesgo: 10,
        min_para_merma: 60,
        estado: 'en_rango',
        ultima_lectura: null,
        valor_en_riesgo_mxn: 0,
      },
    ]
    fetchFalso.mockResolvedValue(respuesta(camaras))

    await expect(obtenerCamaras()).resolves.toEqual(camaras)
    expect(fetchFalso).toHaveBeenCalledWith(
      `${BASE}/camaras`,
      expect.objectContaining({
        headers: expect.any(Headers),
        signal: expect.any(AbortSignal),
      }),
    )
    const [, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(new Headers(init.headers).get('Accept')).toBe('application/json')
  })

  it('fusiona los headers del llamador sin perder los suyos', async () => {
    fetchFalso.mockResolvedValue(respuesta({}))

    await pedir('/prueba', {
      headers: new Headers({ 'X-Prueba': '1' }),
    })

    const [, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(init.headers)
    expect(headers.get('X-Prueba')).toBe('1')
    expect(headers.get('Accept')).toBe('application/json')
  })

  it('respeta la señal del llamador', async () => {
    const controlador = new AbortController()
    fetchFalso.mockImplementation((_url: string, init?: RequestInit) => {
      return new Promise((_resolver, rechazar) => {
        init?.signal?.addEventListener(
          'abort',
          () => rechazar(new DOMException('abortado', 'AbortError')),
          { once: true },
        )
      })
    })

    const peticion = obtenerCamaras(controlador.signal)
    controlador.abort()

    await expect(peticion).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('arma la ruta de lecturas con el id de la cámara', async () => {
    fetchFalso.mockResolvedValue(respuesta([]))

    await expect(obtenerLecturas(3)).resolves.toEqual([])
    expect(fetchFalso).toHaveBeenCalledWith(
      `${BASE}/camaras/3/lecturas`,
      expect.any(Object),
    )
  })

  it('convierte un error HTTP en ErrorApi con el detail de la API', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ detail: 'Cámara no encontrada' }, 404, 'Not Found'),
    )

    const fallo = await obtenerLecturas(99).catch((error: unknown) => error)

    expect(fallo).toBeInstanceOf(ErrorApi)
    expect(fallo).toMatchObject({
      name: 'ErrorApi',
      message: 'Cámara no encontrada',
      status: 404,
      detalle: 'Cámara no encontrada',
    })
  })

  it('usa el status cuando el cuerpo del error no trae detail', async () => {
    fetchFalso.mockResolvedValue(respuesta({}, 500, 'Internal Server Error'))

    const fallo = await obtenerKpis().catch((error: unknown) => error)

    expect(fallo).toMatchObject({
      message: 'La API respondió 500 Internal Server Error',
      detalle: null,
    })
  })

  it('falla claro si no hay VITE_API_URL fuera de desarrollo', async () => {
    vi.mocked(resolverApiUrl).mockReturnValue(null)

    await expect(obtenerHealth()).rejects.toThrow(/VITE_API_URL/)
    expect(fetchFalso).not.toHaveBeenCalled()
  })

  it('corta la petición cuando la API tarda más de 10 s', async () => {
    vi.useFakeTimers()
    fetchFalso.mockImplementation((_url: string, init?: RequestInit) => {
      return new Promise((_resolver, rechazar) => {
        init?.signal?.addEventListener(
          'abort',
          () => rechazar(new DOMException('abortado', 'AbortError')),
          { once: true },
        )
      })
    })

    const peticion = obtenerHealth().catch((error: unknown) => error)
    await vi.advanceTimersByTimeAsync(10_000)
    const error = await peticion

    expect(error).toBeInstanceOf(Error)
    expect((error as Error).message).toContain('tardó más de 10 s')
  })
})

describe('obtenerAlertasActivas', () => {
  const alerta = {
    id: 31,
    camara_id: 1,
    tipo: 'temperatura',
    abierta_en: '2026-11-14T23:00:00+00:00',
    cerrada_en: null,
    atendida_por: null,
    temperatura_max_c: 3.4,
    sms_enviados: 1,
  }

  it('pide las alertas activas del contrato', async () => {
    fetchFalso.mockResolvedValue(respuesta([alerta]))

    await expect(obtenerAlertasActivas()).resolves.toEqual([alerta])
    expect(fetchFalso).toHaveBeenCalledWith(
      `${BASE}/alertas?activas=true&limite=200`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('descarta filas inválidas y normaliza los campos opcionales', async () => {
    fetchFalso.mockResolvedValue(
      respuesta([
        alerta,
        { id: 2, camara_id: '1', tipo: 'temperatura', abierta_en: '...' },
        { id: 3, camara_id: 1, tipo: 4, abierta_en: '...' },
        { id: 4, camara_id: 1, tipo: 'puerta' },
        {
          id: 5,
          camara_id: 2,
          tipo: 'puerta',
          abierta_en: '2026-11-14T23:10:00+00:00',
          cerrada_en: undefined,
          atendida_por: undefined,
          temperatura_max_c: undefined,
          sms_enviados: undefined,
        },
        null,
      ]),
    )

    const alertas = await obtenerAlertasActivas()

    expect(alertas.map((item) => item.id)).toEqual([31, 5])
    expect(alertas[1]).toMatchObject({
      cerrada_en: null,
      atendida_por: null,
      temperatura_max_c: null,
      sms_enviados: 0,
    })
  })

  it('lanza si la respuesta no es un arreglo', async () => {
    fetchFalso.mockResolvedValue(respuesta({ detail: 'contrato roto' }))

    await expect(obtenerAlertasActivas()).rejects.toThrow(/formato inesperado/)
  })
})

describe('atenderAlerta', () => {
  const alerta = {
    id: 31,
    camara_id: 1,
    tipo: 'temperatura',
    abierta_en: '2026-11-14T23:00:00+00:00',
    cerrada_en: null,
    atendida_por: 3,
    temperatura_max_c: 3.4,
    sms_enviados: 1,
  }

  it('manda el POST con la nota y devuelve la alerta actualizada', async () => {
    fetchFalso.mockResolvedValue(respuesta(alerta))

    await expect(atenderAlerta(31, 'Puerta cerrada')).resolves.toEqual(alerta)

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/alertas/31/atender`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ nota: 'Puerta cerrada' })

    const headers = new Headers(init.headers)
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('Accept')).toBe('application/json')
  })

  it('propaga el 409 cuando la alerta ya estaba cerrada', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ detail: 'La alerta ya está cerrada' }, 409, 'Conflict'),
    )

    await expect(atenderAlerta(31)).rejects.toMatchObject({
      name: 'ErrorApi',
      status: 409,
    })
  })
})

describe('obtenerAlertasSeguridad', () => {
  const alerta = {
    id: 1,
    regla_id: '3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41',
    regla: 'Fuerza bruta de tokens',
    severidad: 'high',
    ts: '2026-11-14T23:30:25+00:00',
    ip_origen: '192.168.0.4',
    detalle: {
      clave: 'ip:192.168.0.4',
      rutas: ['/api/telemetria'],
      intentos: 15,
      ventana_s: 300,
    },
    accion: 'bloquear_ip',
    descripcion: 'Descripción del backend',
  }

  it('pide las alertas del detector y las tipa', async () => {
    fetchFalso.mockResolvedValue(respuesta([alerta]))

    await expect(obtenerAlertasSeguridad()).resolves.toEqual([alerta])
    expect(fetchFalso).toHaveBeenCalledWith(
      `${BASE}/seguridad/alertas`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('conserva severidades y acciones desconocidas y normaliza ip_origen ausente', async () => {
    fetchFalso.mockResolvedValue(
      respuesta([
        alerta,
        {
          ...alerta,
          id: 2,
          severidad: 'informational',
          ip_origen: undefined,
        },
        { ...alerta, id: 3, accion: 'notificar' },
        null,
      ]),
    )

    const alertas = await obtenerAlertasSeguridad()

    expect(alertas.map((item) => item.id)).toEqual([1, 2, 3])
    expect(alertas[1]).toMatchObject({
      severidad: 'informational',
      ip_origen: null,
    })
    expect(alertas[2].accion).toBe('notificar')
  })

  it('lanza si la respuesta no es un arreglo para conservar las alertas previas', async () => {
    fetchFalso.mockResolvedValue(respuesta({ detail: 'contrato roto' }))

    await expect(obtenerAlertasSeguridad()).rejects.toThrow(
      /formato inesperado/,
    )
  })
})

describe('auth del cliente', () => {
  it('adjunta el token en Authorization cuando hay sesión', async () => {
    setToken('jwt-de-prueba')
    fetchFalso.mockResolvedValue(respuesta([]))

    await obtenerCamaras()

    const [, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(new Headers(init.headers).get('Authorization')).toBe(
      'Bearer jwt-de-prueba',
    )
  })

  it('no adjunta Authorization al login aunque haya un token viejo', async () => {
    setToken('jwt-viejo')
    fetchFalso.mockResolvedValue(
      respuesta({
        access_token: 'jwt-nuevo',
        token_type: 'bearer',
        expira_en_segundos: 28800,
      }),
    )

    await iniciarSesion('jefe', 'friotrack-demo')

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(init.headers)
    expect(url).toBe(`${BASE}/auth/login`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      usuario: 'jefe',
      password: 'friotrack-demo',
    })
    expect(headers.get('Authorization')).toBeNull()
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  it('un 401 autenticado notifica para cerrar la sesión', async () => {
    setToken('jwt-viejo')
    const oyente = vi.fn()
    const desuscribir = suscribirNoAutorizado(oyente)
    fetchFalso.mockResolvedValue(
      respuesta({ detail: 'No autorizado' }, 401, 'Unauthorized'),
    )

    try {
      await expect(obtenerCamaras()).rejects.toMatchObject({ status: 401 })
      expect(oyente).toHaveBeenCalledTimes(1)
    } finally {
      desuscribir()
    }
  })

  it('un 401 del login no dispara el logout global', async () => {
    setToken('jwt-viejo')
    const oyente = vi.fn()
    const desuscribir = suscribirNoAutorizado(oyente)
    fetchFalso.mockResolvedValue(
      respuesta(
        { detail: 'Usuario o contraseña incorrectos.' },
        401,
        'Unauthorized',
      ),
    )

    try {
      await expect(iniciarSesion('jefe', 'mala')).rejects.toMatchObject({
        status: 401,
      })
      expect(oyente).not.toHaveBeenCalled()
    } finally {
      desuscribir()
    }
  })

  it('no usa un token de sessionStorage antes de que el provider lo restaure', async () => {
    sessionStorage.setItem('friotrack.token', 'token-basura')
    fetchFalso.mockResolvedValue(respuesta([]))

    await obtenerCamaras()

    const [, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(new Headers(init.headers).get('Authorization')).toBeNull()
  })

  it('lee Retry-After de un 429', async () => {
    fetchFalso.mockResolvedValue(
      respuesta(
        { detail: 'Demasiados intentos de inicio de sesión.' },
        429,
        'Too Many Requests',
        { 'Retry-After': '120' },
      ),
    )

    const fallo = await iniciarSesion('jefe', 'mala').catch(
      (error: unknown) => error,
    )

    expect(fallo).toMatchObject({
      name: 'ErrorApi',
      status: 429,
      retryAfterSegundos: 120,
    })
  })

  it('lee Retry-After en formato de fecha HTTP', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-21T07:27:00Z'))
    fetchFalso.mockResolvedValue(
      respuesta({ detail: 'Rate limit' }, 429, 'Too Many Requests', {
        'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT',
      }),
    )

    const fallo = await pedir('/prueba').catch((error: unknown) => error)

    expect(fallo).toMatchObject({ retryAfterSegundos: 60 })
  })

  it('ignora un Retry-After vacío o solo con espacios', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ detail: 'Rate limit' }, 429, 'Too Many Requests', {
        'Retry-After': '   ',
      }),
    )

    const fallo = await pedir('/prueba').catch((error: unknown) => error)

    expect(fallo).toMatchObject({ retryAfterSegundos: null })
  })
})
