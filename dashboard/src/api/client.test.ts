import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ErrorApi,
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
  pedir,
} from './client'
import { resolverApiUrl } from './url'

vi.mock('./url', () => ({
  resolverApiUrl: vi.fn(() => 'http://api.prueba.mx/api'),
}))

const BASE = 'http://api.prueba.mx/api'
const fetchFalso = vi.fn()

function respuesta(datos: unknown, estado = 200, texto = 'OK'): Response {
  return {
    ok: estado >= 200 && estado < 300,
    status: estado,
    statusText: texto,
    json: async () => datos,
  } as unknown as Response
}

beforeEach(() => {
  fetchFalso.mockReset()
  vi.stubGlobal('fetch', fetchFalso)
  vi.mocked(resolverApiUrl).mockReturnValue(BASE)
})

afterEach(() => {
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
    })
  })

  it('usa el status cuando el cuerpo del error no trae detail', async () => {
    fetchFalso.mockResolvedValue(respuesta({}, 500, 'Internal Server Error'))

    await expect(obtenerKpis()).rejects.toThrow(
      'La API respondió 500 Internal Server Error',
    )
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
