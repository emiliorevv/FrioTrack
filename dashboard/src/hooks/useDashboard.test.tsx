import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
} from '../api/client'
import { useStreamEvent } from '../realtime/StreamProvider'
import type { Camara, Kpis, Lectura } from '../types'
import { fusionarCamaras, useDashboard } from './useDashboard'

vi.mock('../api/client', () => ({
  obtenerHealth: vi.fn(),
  obtenerCamaras: vi.fn(),
  obtenerKpis: vi.fn(),
  obtenerLecturas: vi.fn(),
}))

vi.mock('../realtime/StreamProvider', () => ({
  useStreamEvent: vi.fn(),
}))

type Oyente = (evento: MessageEvent<string>) => void

const oyentes = new Map<string, Oyente>()

const kpis: Kpis = {
  pct_tiempo_en_rango_24h: 97.3,
  alertas_activas: 1,
  tiempo_respuesta_promedio_min: 6.5,
  valor_en_riesgo_mxn: 4850,
  merma_hoy_mxn: 0,
  merma_mes_mxn: 1720,
}

function crearCamaras(): Camara[] {
  return [
    {
      id: 1,
      nombre: 'Pescados y mariscos',
      rango_min_c: 0,
      rango_max_c: 2,
      min_para_riesgo: 10,
      min_para_merma: 60,
      estado: 'en_rango',
      ultima_lectura: {
        ts: '2026-11-14T10:00:00+00:00',
        temperatura_c: 1,
        humedad_pct: 80,
        puerta_abierta: false,
      },
      valor_en_riesgo_mxn: 0,
    },
    {
      id: 2,
      nombre: 'Carnes y aves',
      rango_min_c: 0,
      rango_max_c: 4,
      min_para_riesgo: 15,
      min_para_merma: 120,
      estado: 'en_rango',
      ultima_lectura: {
        ts: '2026-11-14T10:00:01+00:00',
        temperatura_c: 2.5,
        humedad_pct: 80,
        puerta_abierta: false,
      },
      valor_en_riesgo_mxn: 0,
    },
  ]
}

function crearLectura(camaraId: number, temperatura: number): Lectura {
  return {
    id: camaraId * 100,
    ts: '2026-11-14T10:00:00+00:00',
    recibida_en: '2026-11-14T10:00:01+00:00',
    temperatura_c: temperatura,
    humedad_pct: 80,
    puerta_abierta: false,
    sospechosa: false,
  }
}

function emitir(evento: string, datos: unknown) {
  const oyente = oyentes.get(evento)
  if (!oyente) {
    throw new Error(`Sin oyente para ${evento}`)
  }
  oyente(new MessageEvent(evento, { data: JSON.stringify(datos) }))
}

beforeEach(() => {
  vi.clearAllMocks()
  oyentes.clear()
  vi.mocked(useStreamEvent).mockImplementation((evento, oyente) => {
    oyentes.set(evento, oyente)
  })
  vi.mocked(obtenerHealth).mockResolvedValue({ ok: true, escala_tiempo: 30 })
  vi.mocked(obtenerCamaras).mockResolvedValue(crearCamaras())
  vi.mocked(obtenerKpis).mockResolvedValue(kpis)
  vi.mocked(obtenerLecturas).mockImplementation(async (id) => [
    crearLectura(id, 1 + id),
  ])
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useDashboard', () => {
  it('carga health, cámaras, KPIs y una serie por cámara', async () => {
    const { result } = renderHook(() => useDashboard())

    expect(result.current.cargando).toBe(true)

    await waitFor(() => {
      expect(result.current.series[1]).toEqual([2])
      expect(result.current.series[2]).toEqual([3])
    })
    await waitFor(() => {
      expect(result.current.health).toEqual({ ok: true, escala_tiempo: 30 })
    })

    expect(result.current.camaras).toHaveLength(2)
    expect(result.current.kpis).toEqual(kpis)
    expect(result.current.cargando).toBe(false)
    expect(result.current.error).toBeNull()
    expect(result.current.actualizadoEn).toBeInstanceOf(Date)
    expect(obtenerLecturas).toHaveBeenCalledTimes(2)
  })

  it('muestra cámaras y KPIs aunque /health falle', async () => {
    vi.mocked(obtenerHealth).mockRejectedValueOnce(
      new Error('health no disponible'),
    )

    const { result } = renderHook(() => useDashboard())

    await waitFor(() => expect(result.current.camaras).toHaveLength(2))

    expect(result.current.health).toBeNull()
    expect(result.current.kpis).toEqual(kpis)
    expect(result.current.cargando).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('solo reintenta /health si sigue en null', async () => {
    vi.mocked(obtenerHealth).mockRejectedValueOnce(
      new Error('health no disponible'),
    )

    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.camaras).toHaveLength(2))
    expect(result.current.health).toBeNull()

    await act(async () => {
      await result.current.refrescar()
    })

    expect(result.current.health).toEqual({ ok: true, escala_tiempo: 30 })
  })

  it('no vuelve a pedir /health cuando ya lo tiene', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.health).not.toBeNull())

    await act(async () => {
      await result.current.refrescar()
    })

    expect(obtenerHealth).toHaveBeenCalledTimes(1)
  })

  it('no reintenta /health desde el polling si la carga inicial falló', async () => {
    vi.useFakeTimers()
    vi.mocked(obtenerHealth).mockRejectedValueOnce(
      new Error('health no disponible'),
    )
    vi.mocked(obtenerCamaras).mockRejectedValueOnce(new Error('sin red'))

    const { result } = renderHook(() => useDashboard())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(obtenerHealth).toHaveBeenCalledTimes(1)
    expect(result.current.error).toBe('sin red')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })

    expect(obtenerHealth).toHaveBeenCalledTimes(1)
  })

  it('no vuelve a pedir las series en los refrescos', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.series[1]).toEqual([2]))
    expect(obtenerLecturas).toHaveBeenCalledTimes(2)

    await act(async () => {
      await result.current.refrescar()
    })

    expect(obtenerLecturas).toHaveBeenCalledTimes(2)
  })

  it('deja sin sparkline la cámara cuya serie falla', async () => {
    vi.mocked(obtenerLecturas).mockImplementation(async (id) => {
      if (id === 1) {
        throw new Error('sin lecturas')
      }
      return [crearLectura(id, 5)]
    })

    const { result } = renderHook(() => useDashboard())

    await waitFor(() => expect(result.current.series[2]).toEqual([5]))

    expect(result.current.series[1]).toBeUndefined()
    expect(result.current.error).toBeNull()
    expect(result.current.cargando).toBe(false)
  })

  it('expone el error inicial y refrescar lo limpia al reintentar', async () => {
    vi.mocked(obtenerCamaras).mockRejectedValueOnce(
      new Error('La API no responde'),
    )

    const { result } = renderHook(() => useDashboard())

    await waitFor(() => expect(result.current.error).toBe('La API no responde'))
    expect(result.current.cargando).toBe(false)
    expect(result.current.camaras).toEqual([])
    expect(obtenerLecturas).not.toHaveBeenCalled()

    await act(async () => {
      await result.current.refrescar()
    })

    expect(result.current.error).toBeNull()
    expect(result.current.camaras).toHaveLength(2)
    expect(result.current.kpis).toEqual(kpis)
    expect(obtenerLecturas).toHaveBeenCalledTimes(2)
  })

  it('conserva los datos y expone el error de un refresco fallido', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.camaras).toHaveLength(2))

    vi.mocked(obtenerCamaras).mockRejectedValueOnce(new Error('sin red'))

    await act(async () => {
      await result.current.refrescar()
    })

    expect(result.current.error).toBe('sin red')
    expect(result.current.camaras).toHaveLength(2)
    expect(result.current.kpis).toEqual(kpis)
  })

  it('conserva una lectura SSE más nueva al aplicar un refresco HTTP', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.series[1]).toEqual([2]))

    act(() => {
      emitir('lectura', {
        camara_id: 1,
        ts: '2026-11-14T10:05:00+00:00',
        temperatura_c: 4.2,
        humedad_pct: 81,
        puerta_abierta: true,
        estado_camara: 'critica',
      })
    })

    const httpViejo = crearCamaras().map((camara) =>
      camara.id === 1 ? { ...camara, valor_en_riesgo_mxn: 999 } : camara,
    )
    vi.mocked(obtenerCamaras).mockResolvedValueOnce(httpViejo)

    await act(async () => {
      await result.current.refrescar()
    })

    expect(result.current.camaras[0]).toMatchObject({
      estado: 'critica',
      valor_en_riesgo_mxn: 999,
      ultima_lectura: {
        ts: '2026-11-14T10:05:00+00:00',
        temperatura_c: 4.2,
      },
    })
  })

  it('una respuesta vieja que resuelve tarde no pisa a la nueva', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.camaras).toHaveLength(2))

    const viejas = crearCamaras().map((camara) => ({
      ...camara,
      valor_en_riesgo_mxn: 111,
    }))
    const nuevas = crearCamaras().map((camara) => ({
      ...camara,
      valor_en_riesgo_mxn: 222,
    }))
    let resolverVieja!: (camaras: Camara[]) => void
    const pendienteVieja = new Promise<Camara[]>((resolver) => {
      resolverVieja = resolver
    })

    vi.mocked(obtenerCamaras)
      .mockImplementationOnce(() => pendienteVieja)
      .mockResolvedValueOnce(nuevas)
    vi.mocked(obtenerKpis)
      .mockResolvedValueOnce({ ...kpis, valor_en_riesgo_mxn: 111 })
      .mockResolvedValueOnce({ ...kpis, valor_en_riesgo_mxn: 222 })

    let primera!: Promise<void>
    let segunda!: Promise<void>
    await act(async () => {
      primera = result.current.refrescar()
      segunda = result.current.refrescar()
      await segunda
    })

    expect(result.current.camaras[0].valor_en_riesgo_mxn).toBe(222)
    expect(result.current.kpis?.valor_en_riesgo_mxn).toBe(222)

    await act(async () => {
      resolverVieja(viejas)
      await primera
    })

    expect(result.current.camaras[0].valor_en_riesgo_mxn).toBe(222)
    expect(result.current.kpis?.valor_en_riesgo_mxn).toBe(222)
  })

  it('actualiza la cámara y la serie con el evento lectura', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.series[1]).toEqual([2]))
    const anterior = result.current.actualizadoEn

    act(() => {
      emitir('lectura', {
        camara_id: 1,
        ts: '2026-11-14T10:05:00+00:00',
        temperatura_c: 4.2,
        humedad_pct: 81,
        puerta_abierta: true,
        estado_camara: 'critica',
      })
    })

    expect(result.current.camaras[0]).toMatchObject({
      estado: 'critica',
      ultima_lectura: {
        ts: '2026-11-14T10:05:00+00:00',
        temperatura_c: 4.2,
        humedad_pct: 81,
        puerta_abierta: true,
      },
    })
    expect(result.current.series[1]).toEqual([2, 4.2])
    expect(result.current.actualizadoEn).not.toBe(anterior)
  })

  it('reemplaza los KPIs con el evento kpis', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.kpis).toEqual(kpis))

    const nuevos: Kpis = {
      ...kpis,
      alertas_activas: 3,
      valor_en_riesgo_mxn: 1720,
    }

    act(() => {
      emitir('kpis', nuevos)
    })

    expect(result.current.kpis).toEqual(nuevos)
  })

  it('ignora eventos con forma inválida', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.series[1]).toEqual([2]))

    act(() => {
      emitir('lectura', { camara_id: 1 })
      emitir('kpis', { alertas_activas: 9 })
    })

    expect(result.current.camaras[0].estado).toBe('en_rango')
    expect(result.current.series[1]).toEqual([2])
    expect(result.current.kpis).toEqual(kpis)
  })
})

describe('fusionarCamaras', () => {
  it('conserva lectura y estado actuales si son más nuevos, pero toma el valor HTTP', () => {
    const [pescados] = crearCamaras()
    const actual: Camara = {
      ...pescados,
      estado: 'critica',
      ultima_lectura: {
        ...pescados.ultima_lectura!,
        ts: '2026-11-14T10:05:00+00:00',
        temperatura_c: 4.2,
      },
    }
    const http: Camara = {
      ...pescados,
      estado: 'en_rango',
      valor_en_riesgo_mxn: 500,
      ultima_lectura: {
        ...pescados.ultima_lectura!,
        ts: '2026-11-14T09:00:00+00:00',
        temperatura_c: 1,
      },
    }

    const [resultado] = fusionarCamaras([actual], [http])

    expect(resultado).toMatchObject({
      estado: 'critica',
      valor_en_riesgo_mxn: 500,
      ultima_lectura: {
        ts: '2026-11-14T10:05:00+00:00',
        temperatura_c: 4.2,
      },
    })
  })

  it('usa la respuesta HTTP cuando su lectura es más nueva', () => {
    const [pescados] = crearCamaras()
    const actual: Camara = {
      ...pescados,
      estado: 'critica',
      ultima_lectura: {
        ...pescados.ultima_lectura!,
        ts: '2026-11-14T09:00:00+00:00',
      },
    }
    const http: Camara = {
      ...pescados,
      estado: 'alerta',
      valor_en_riesgo_mxn: 300,
      ultima_lectura: {
        ...pescados.ultima_lectura!,
        ts: '2026-11-14T10:05:00+00:00',
        temperatura_c: 3.3,
      },
    }

    const [resultado] = fusionarCamaras([actual], [http])

    expect(resultado).toEqual(http)
  })

  it('usa la respuesta para cámaras nuevas o sin lectura y descarta las ausentes', () => {
    const [pescados, carnes] = crearCamaras()
    const nueva: Camara = {
      ...pescados,
      id: 7,
      nombre: 'Nueva',
      valor_en_riesgo_mxn: 50,
    }
    const httpCarnes: Camara = {
      ...carnes,
      valor_en_riesgo_mxn: 80,
    }

    const resultado = fusionarCamaras(
      [pescados, { ...carnes, ultima_lectura: null }],
      [nueva, httpCarnes],
    )

    expect(resultado).toEqual([nueva, httpCarnes])
  })
})
