import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  actualizarCamara,
  actualizarLote,
  actualizarSensor,
  atenderAlerta,
  crearCamara,
  crearLote,
  crearSensor,
  eliminarCamara,
  eliminarLote,
  eliminarSensor,
  ErrorApi,
  iniciarSesion,
  listarSensores,
  marcarLoteMerma,
  rotarTokenSensor,
  obtenerAlertasActivas,
  obtenerAlertasSeguridad,
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
  obtenerLotes,
  pedir,
  registrar,
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

  it('valida el listado de cámaras y filtra filas inválidas', async () => {
    const valida = {
      id: 1,
      nombre: 'Pescados y mariscos',
      rango_min_c: 0,
      rango_max_c: 2,
      min_para_riesgo: 10,
      min_para_merma: 60,
      estado: 'en_rango',
      ultima_lectura: null,
      valor_en_riesgo_mxn: 0,
    }
    fetchFalso.mockResolvedValue(
      respuesta([
        valida,
        { ...valida, id: 2, estado: 'raro' },
        { ...valida, id: 3, rango_min_c: 'frío' },
        null,
      ]),
    )

    await expect(obtenerCamaras()).resolves.toEqual([valida])
  })

  it('lanza si el listado de cámaras no es un arreglo', async () => {
    fetchFalso.mockResolvedValue(respuesta({ detail: 'contrato roto' }))

    await expect(obtenerCamaras()).rejects.toThrow(
      /formato inesperado para las cámaras/,
    )
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

  it('extrae el msg real de un detail[] de FastAPI', async () => {
    fetchFalso.mockResolvedValue(
      respuesta(
        {
          detail: [
            {
              type: 'value_error',
              loc: ['body', 'min_para_merma'],
              msg: 'min_para_merma debe ser mayor que min_para_riesgo',
            },
          ],
        },
        422,
        'Unprocessable Entity',
      ),
    )

    const fallo = await crearCamara({
      nombre: 'Congelador',
      rango_min_c: -18,
      rango_max_c: -15,
      min_para_riesgo: 60,
      min_para_merma: 10,
    }).catch((error: unknown) => error)

    expect(fallo).toMatchObject({
      name: 'ErrorApi',
      status: 422,
      detalle: 'min_para_merma debe ser mayor que min_para_riesgo',
    })
    expect((fallo as Error).message).toContain('min_para_merma')
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

  it('no adjunta Authorization al registro aunque haya un token viejo', async () => {
    setToken('jwt-viejo')
    fetchFalso.mockResolvedValue(
      respuesta(
        {
          access_token: 'jwt-nuevo',
          token_type: 'bearer',
          expira_en_segundos: 28800,
        },
        201,
        'Created',
      ),
    )

    const sesion = await registrar(
      'Taquería del Norte',
      'dueno-nuevo',
      'friotrack-demo',
    )

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(init.headers)
    expect(url).toBe(`${BASE}/auth/registro`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      restaurante: 'Taquería del Norte',
      usuario: 'dueno-nuevo',
      password: 'friotrack-demo',
    })
    expect(headers.get('Authorization')).toBeNull()
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(sesion.access_token).toBe('jwt-nuevo')
  })

  it('rechaza una sesión de registro con contrato inválido', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ access_token: '' }, 201, 'Created'),
    )

    await expect(
      registrar('Taquería del Norte', 'dueno-nuevo', 'friotrack-demo'),
    ).rejects.toThrow('La API devolvió una sesión inválida.')
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

describe('administración de cámaras', () => {
  const camara = {
    id: 7,
    nombre: 'Congelador nuevo',
    rango_min_c: -22,
    rango_max_c: -18,
    min_para_riesgo: 10,
    min_para_merma: 60,
    estado: 'en_rango',
    ultima_lectura: null,
    valor_en_riesgo_mxn: 0,
    valor_inventario_mxn: 0,
  }

  const datos = {
    nombre: 'Congelador nuevo',
    rango_min_c: -22,
    rango_max_c: -18,
    min_para_riesgo: 10,
    min_para_merma: 60,
  }

  it('crea una cámara con POST y valida la respuesta', async () => {
    fetchFalso.mockResolvedValue(respuesta(camara, 201, 'Created'))

    await expect(crearCamara(datos)).resolves.toEqual(camara)

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/camaras`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual(datos)
    expect(new Headers(init.headers).get('Content-Type')).toBe(
      'application/json',
    )
  })

  it('devuelve null si el 201 no normaliza, sin reportar un fallo de alta', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ ...camara, rango_min_c: 'frío' }, 201, 'Created'),
    )

    await expect(crearCamara(datos)).resolves.toBeNull()
  })

  it('devuelve null si el PATCH responde un shape inválido', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ ...camara, estado: 'desconocido' }),
    )

    await expect(actualizarCamara(7, { nombre: 'X' })).resolves.toBeNull()
  })

  it('actualiza con PATCH y devuelve la cámara final', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ ...camara, nombre: 'Congelador 2' }),
    )

    await expect(
      actualizarCamara(7, { nombre: 'Congelador 2' }),
    ).resolves.toMatchObject({ id: 7, nombre: 'Congelador 2' })

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/camaras/7`)
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(String(init.body))).toEqual({ nombre: 'Congelador 2' })
  })

  it('elimina con DELETE y acepta el 204 sin cuerpo', async () => {
    fetchFalso.mockResolvedValue(respuesta(undefined, 204, 'No Content'))

    await expect(eliminarCamara(7)).resolves.toBeUndefined()

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/camaras/7`)
    expect(init.method).toBe('DELETE')
  })

  it('propaga el 409 cuando la cámara tiene datos asociados', async () => {
    fetchFalso.mockResolvedValue(
      respuesta(
        {
          detail:
            'La cámara tiene datos asociados; desactívala o elimina primero sus sensores.',
        },
        409,
        'Conflict',
      ),
    )

    await expect(eliminarCamara(7)).rejects.toMatchObject({
      name: 'ErrorApi',
      status: 409,
      detalle:
        'La cámara tiene datos asociados; desactívala o elimina primero sus sensores.',
    })
  })
})

describe('sensores', () => {
  const sensor = {
    id: 'S-1234abcd',
    camara_id: 1,
    camara_nombre: 'Pescados y mariscos',
    activo: true,
    ultima_lectura: null,
  }

  it('lista sensores y descarta filas inválidas sin exponer token_hash', async () => {
    fetchFalso.mockResolvedValue(
      respuesta([
        { ...sensor, token_hash: 'no-debe-salir' },
        { ...sensor, id: 'S-válido', camara_nombre: undefined },
        { id: 4, camara_id: 1, activo: true },
        { id: 'S-sin-camara', activo: true },
        null,
      ]),
    )

    const sensores = await listarSensores()

    expect(sensores).toEqual([
      sensor,
      { ...sensor, id: 'S-válido', camara_nombre: '' },
    ])
    expect(sensores[0]).not.toHaveProperty('token_hash')
    expect(fetchFalso).toHaveBeenCalledWith(
      `${BASE}/sensores`,
      expect.any(Object),
    )
  })

  it('lanza si el listado no es un arreglo', async () => {
    fetchFalso.mockResolvedValue(respuesta({ detail: 'contrato roto' }))

    await expect(listarSensores()).rejects.toThrow(/formato inesperado/)
  })

  it('crea un sensor sin body y devuelve su token una sola vez', async () => {
    fetchFalso.mockResolvedValue(
      respuesta(
        {
          sensor: {
            id: 'S-1234abcd',
            camara_id: 1,
            activo: true,
          },
          token: 'tok-en-claro',
        },
        201,
        'Created',
      ),
    )

    await expect(crearSensor(1)).resolves.toEqual({
      sensor: { ...sensor, camara_nombre: '' },
      token: 'tok-en-claro',
    })

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/camaras/1/sensores`)
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
  })

  it('rota el token con POST y valida la respuesta', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({
        sensor: { id: 'S-1234abcd', camara_id: 1, activo: false },
        token: 'tok-rotado',
      }),
    )

    await expect(rotarTokenSensor('S-1234abcd')).resolves.toMatchObject({
      token: 'tok-rotado',
      sensor: { activo: false },
    })

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/sensores/S-1234abcd/rotar-token`)
    expect(init.method).toBe('POST')
  })

  it('rechaza una respuesta de token sin token', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ sensor: { id: 'S-1', camara_id: 1, activo: true } }),
    )

    await expect(crearSensor(1)).rejects.toThrow(
      'La API devolvió un sensor inválido.',
    )
  })

  it('activa o desactiva con PATCH', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ id: 'S-1234abcd', camara_id: 1, activo: false }),
    )

    await expect(
      actualizarSensor('S-1234abcd', { activo: false }),
    ).resolves.toMatchObject({ id: 'S-1234abcd', activo: false })

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/sensores/S-1234abcd`)
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(String(init.body))).toEqual({ activo: false })
  })

  it('elimina con DELETE y acepta el 204', async () => {
    fetchFalso.mockResolvedValue(respuesta(undefined, 204, 'No Content'))

    await expect(eliminarSensor('S-1234abcd')).resolves.toBeUndefined()

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/sensores/S-1234abcd`)
    expect(init.method).toBe('DELETE')
  })

  it('propaga el 409 cuando el sensor ya tiene lecturas', async () => {
    fetchFalso.mockResolvedValue(
      respuesta(
        {
          detail:
            'El sensor tiene lecturas asociadas; desactívalo en lugar de eliminarlo.',
        },
        409,
        'Conflict',
      ),
    )

    await expect(eliminarSensor('S-1234abcd')).rejects.toMatchObject({
      name: 'ErrorApi',
      status: 409,
    })
  })
})

describe('inventario', () => {
  const lote = {
    id: 4,
    producto: 'Salmón fresco',
    camara_id: 1,
    cantidad: 2.5,
    unidad: 'kg',
    costo_total_mxn: 450.5,
    caducidad: '2026-12-31',
    estado: 'ok',
    merma_en: null,
  }

  const datos = {
    producto: 'Salmón fresco',
    camara_id: 1,
    cantidad: 2.5,
    unidad: 'kg' as const,
    costo_total_mxn: 450.5,
    caducidad: '2026-12-31',
  }

  it('lista lotes sin filtros y valida el shape', async () => {
    fetchFalso.mockResolvedValue(
      respuesta([
        { ...lote, token_hash: 'no-debe-salir' },
        { ...lote, id: 5, unidad: 'caja' },
        { ...lote, id: 6, cantidad: 0 },
        { ...lote, id: 7, camara_id: '1' },
        null,
      ]),
    )

    await expect(obtenerLotes()).resolves.toEqual([lote])
    expect(fetchFalso).toHaveBeenCalledWith(
      `${BASE}/lotes`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('arma los filtros de cámara y estado', async () => {
    fetchFalso.mockResolvedValue(respuesta([]))

    await obtenerLotes({ camara_id: 3, estado: 'en_riesgo' })

    expect(fetchFalso).toHaveBeenCalledWith(
      `${BASE}/lotes?camara_id=3&estado=en_riesgo`,
      expect.any(Object),
    )
  })

  it('lanza si el listado no es un arreglo', async () => {
    fetchFalso.mockResolvedValue(respuesta({ detail: 'contrato roto' }))

    await expect(obtenerLotes()).rejects.toThrow(/formato inesperado/)
  })

  it('crea un lote con POST y normaliza la respuesta', async () => {
    fetchFalso.mockResolvedValue(respuesta(lote, 201, 'Created'))

    await expect(crearLote(datos)).resolves.toEqual(lote)

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/lotes`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual(datos)
  })

  it('devuelve null si el 201 no normaliza', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ ...lote, estado: 'desconocido' }, 201, 'Created'),
    )

    await expect(crearLote(datos)).resolves.toBeNull()
  })

  it('actualiza y mueve el lote con PATCH', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({ ...lote, camara_id: 2, cantidad: 3 }),
    )

    await expect(
      actualizarLote(4, { camara_id: 2, cantidad: 3 }),
    ).resolves.toMatchObject({ id: 4, camara_id: 2, cantidad: 3 })

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/lotes/4`)
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(String(init.body))).toEqual({ camara_id: 2, cantidad: 3 })
  })

  it('elimina con DELETE y acepta 204', async () => {
    fetchFalso.mockResolvedValue(respuesta(undefined, 204, 'No Content'))

    await expect(eliminarLote(4)).resolves.toBeUndefined()

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/lotes/4`)
    expect(init.method).toBe('DELETE')
  })

  it('propaga el 409 al borrar una merma', async () => {
    const detalle =
      'El lote ya está en merma; no se puede eliminar del historial.'
    fetchFalso.mockResolvedValue(
      respuesta({ detail: detalle }, 409, 'Conflict'),
    )

    await expect(eliminarLote(4)).rejects.toMatchObject({
      name: 'ErrorApi',
      status: 409,
      detalle,
    })
  })

  it('marca merma con POST y devuelve el lote actualizado', async () => {
    fetchFalso.mockResolvedValue(
      respuesta({
        ...lote,
        estado: 'merma',
        merma_en: '2026-11-16T18:00:00+00:00',
      }),
    )

    await expect(marcarLoteMerma(4)).resolves.toMatchObject({
      id: 4,
      estado: 'merma',
      merma_en: '2026-11-16T18:00:00+00:00',
    })

    const [url, init] = fetchFalso.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/lotes/4/merma`)
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
  })
})
