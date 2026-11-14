import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ErrorApi,
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
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
        headers: expect.objectContaining({ Accept: 'application/json' }),
        signal: expect.any(AbortSignal),
      }),
    )
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
    vi.spyOn(AbortSignal, 'timeout').mockReturnValue(AbortSignal.abort())
    fetchFalso.mockImplementation((_url: string, init?: RequestInit) => {
      expect(init?.signal?.aborted).toBe(true)
      return Promise.reject(
        new DOMException('The operation timed out.', 'TimeoutError'),
      )
    })

    await expect(obtenerHealth()).rejects.toThrow('tardó más de 10 s')
  })
})
