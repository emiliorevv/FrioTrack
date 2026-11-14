import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
} from '../api/client'
import { useStreamEvent } from '../realtime/StreamProvider'
import type { Camara, Kpis, Lectura } from '../types'
import { useDashboard } from './useDashboard'

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

describe('useDashboard', () => {
  it('carga health, cámaras, KPIs y una serie por cámara', async () => {
    const { result } = renderHook(() => useDashboard())

    expect(result.current.cargando).toBe(true)

    await waitFor(() => {
      expect(result.current.series[1]).toEqual([2])
      expect(result.current.series[2]).toEqual([3])
    })

    expect(result.current.health).toEqual({ ok: true, escala_tiempo: 30 })
    expect(result.current.camaras).toHaveLength(2)
    expect(result.current.kpis).toEqual(kpis)
    expect(result.current.cargando).toBe(false)
    expect(result.current.error).toBeNull()
    expect(result.current.actualizadoEn).toBeInstanceOf(Date)
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

    await act(async () => {
      await result.current.refrescar()
    })

    expect(result.current.error).toBeNull()
    expect(result.current.camaras).toHaveLength(2)
    expect(result.current.kpis).toEqual(kpis)
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
