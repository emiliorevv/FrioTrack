import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  atenderAlerta as atenderAlertaApi,
  ErrorApi,
  obtenerAlertasActivas,
  obtenerAlertasSeguridad,
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
} from '../api/client'
import { useStreamEvent, useStreamReconexion } from '../realtime/StreamProvider'
import type {
  AlertaOperativa,
  AlertaSeguridad,
  Camara,
  Health,
  Kpis,
  Lectura,
  PuntoSerie,
} from '../types'
import {
  fusionarCamaras,
  fusionarSeries,
  MAX_PUNTOS_SERIE,
  RETRASO_ALERTAS_ACTIVAS_MS,
  useDashboard,
} from './useDashboard'

vi.mock('../api/client', () => {
  class ErrorApi extends Error {
    readonly status: number

    constructor(mensaje: string, status: number) {
      super(mensaje)
      this.name = 'ErrorApi'
      this.status = status
    }
  }

  return {
    atenderAlerta: vi.fn(),
    ErrorApi,
    obtenerAlertasActivas: vi.fn(),
    obtenerAlertasSeguridad: vi.fn(),
    obtenerHealth: vi.fn(),
    obtenerCamaras: vi.fn(),
    obtenerKpis: vi.fn(),
    obtenerLecturas: vi.fn(),
  }
})

vi.mock('../realtime/StreamProvider', () => ({
  useStreamEvent: vi.fn(),
  useStreamReconexion: vi.fn(() => 0),
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

const alertaSeguridad: AlertaSeguridad = {
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
}

const alertaOperativa: AlertaOperativa = {
  id: 31,
  camara_id: 1,
  tipo: 'temperatura',
  abierta_en: '2026-11-14T10:00:00+00:00',
  cerrada_en: null,
  atendida_por: null,
  temperatura_max_c: 3.4,
  sms_enviados: 1,
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

function crearLectura(
  camaraId: number,
  temperatura: number,
  ts = '2026-11-14T10:00:00+00:00',
): Lectura {
  return {
    id: camaraId * 100,
    ts,
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
  vi.mocked(useStreamReconexion).mockReturnValue(0)
  vi.mocked(obtenerHealth).mockResolvedValue({ ok: true, escala_tiempo: 30 })
  vi.mocked(obtenerCamaras).mockResolvedValue(crearCamaras())
  vi.mocked(obtenerKpis).mockResolvedValue(kpis)
  vi.mocked(obtenerAlertasSeguridad).mockResolvedValue([alertaSeguridad])
  vi.mocked(obtenerAlertasActivas).mockResolvedValue([alertaOperativa])
  vi.mocked(atenderAlertaApi).mockResolvedValue({
    ...alertaOperativa,
    atendida_por: 3,
  })
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
    await waitFor(() =>
      expect(result.current.alertasSeguridad).toEqual([alertaSeguridad]),
    )
    await waitFor(() =>
      expect(result.current.alertasActivas).toEqual([alertaOperativa]),
    )

    expect(result.current.camaras).toHaveLength(2)
    expect(result.current.kpis).toEqual(kpis)
    expect(result.current.alertasSeguridad).toEqual([alertaSeguridad])
    expect(result.current.alertasCargadas).toBe(true)
    expect(result.current.errorAlertasSeguridad).toBeNull()
    expect(result.current.alertasActivas).toEqual([alertaOperativa])
    expect(result.current.cargandoAlertas).toBe(false)
    expect(result.current.errorAlertas).toBeNull()
    expect(result.current.atendiendo).toEqual({})
    expect(result.current.cargando).toBe(false)
    expect(result.current.errorResumen).toBeNull()
    expect(result.current.ultimoExitoHttp).toBeInstanceOf(Date)
    expect(result.current.ultimaActividadSse).toBeNull()
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
    expect(result.current.errorResumen).toBeNull()
  })

  it('muestra cámaras y KPIs aunque seguridad falle en la carga inicial', async () => {
    vi.mocked(obtenerAlertasSeguridad).mockRejectedValueOnce(
      new Error('seguridad no disponible'),
    )

    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.camaras).toHaveLength(2))
    await waitFor(() =>
      expect(result.current.errorAlertasSeguridad).toBe(
        'seguridad no disponible',
      ),
    )

    expect(result.current.alertasSeguridad).toEqual([])
    expect(result.current.alertasCargadas).toBe(false)
    expect(result.current.errorAlertasSeguridad).toBe('seguridad no disponible')
    expect(result.current.kpis).toEqual(kpis)
    expect(result.current.errorResumen).toBeNull()
  })

  it('conserva las alertas previas si falla un refresco de seguridad', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() =>
      expect(result.current.alertasSeguridad).toEqual([alertaSeguridad]),
    )

    vi.mocked(obtenerAlertasSeguridad).mockRejectedValueOnce(
      new Error('seguridad no disponible'),
    )

    await act(async () => {
      await result.current.refrescar()
    })

    expect(result.current.alertasSeguridad).toEqual([alertaSeguridad])
    expect(result.current.alertasCargadas).toBe(true)
    expect(result.current.errorAlertasSeguridad).toBe('seguridad no disponible')
    expect(result.current.camaras).toHaveLength(2)
    expect(result.current.kpis).toEqual(kpis)
    expect(result.current.errorResumen).toBeNull()
  })

  it('no bloquea cámaras y KPIs con una respuesta lenta de alertas', async () => {
    let resolverAlertas!: (alertas: AlertaSeguridad[]) => void
    const pendiente = new Promise<AlertaSeguridad[]>((resolve) => {
      resolverAlertas = resolve
    })
    vi.mocked(obtenerAlertasSeguridad).mockReturnValueOnce(pendiente)

    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.camaras).toHaveLength(2))

    expect(result.current.cargando).toBe(false)
    expect(result.current.alertasCargadas).toBe(false)
    expect(result.current.errorAlertasSeguridad).toBeNull()

    await act(async () => {
      resolverAlertas([alertaSeguridad])
    })

    await waitFor(() =>
      expect(result.current.alertasSeguridad).toEqual([alertaSeguridad]),
    )
  })

  it('conserva alertas frescas aunque falle /camaras', async () => {
    vi.mocked(obtenerCamaras).mockRejectedValueOnce(new Error('camaras caídas'))

    const { result } = renderHook(() => useDashboard())

    await waitFor(() =>
      expect(result.current.alertasSeguridad).toEqual([alertaSeguridad]),
    )

    expect(result.current.alertasCargadas).toBe(true)
    expect(result.current.camaras).toEqual([])
    expect(result.current.errorResumen).toBe('camaras caídas')
    expect(result.current.errorAlertasSeguridad).toBeNull()
  })

  it('un evento de alerta no cancela la carga de seguridad', async () => {
    vi.useFakeTimers()
    let resolverAlertas!: (alertas: AlertaSeguridad[]) => void
    const pendiente = new Promise<AlertaSeguridad[]>((resolve) => {
      resolverAlertas = resolve
    })
    vi.mocked(obtenerAlertasSeguridad).mockReturnValueOnce(pendiente)

    const { result } = renderHook(() => useDashboard())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.camaras).toHaveLength(2)

    act(() => {
      emitir('alerta_abierta', { id: 1 })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
      await Promise.resolve()
    })

    await act(async () => {
      resolverAlertas([alertaSeguridad])
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(result.current.alertasSeguridad).toEqual([alertaSeguridad])
  })

  it('actualiza las alertas de seguridad en el polling', async () => {
    vi.useFakeTimers()
    const nueva: AlertaSeguridad = {
      ...alertaSeguridad,
      id: 2,
      regla: 'Lecturas imposibles',
      severidad: 'medium',
      accion: 'marcar_lecturas',
    }

    const { result } = renderHook(() => useDashboard())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(result.current.alertasSeguridad).toEqual([alertaSeguridad])

    vi.mocked(obtenerAlertasSeguridad).mockResolvedValueOnce([nueva])
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })

    expect(result.current.alertasSeguridad).toEqual([nueva])
    expect(result.current.errorAlertasSeguridad).toBeNull()
  })

  it('actualiza las alertas activas en el polling', async () => {
    vi.useFakeTimers()
    const nueva: AlertaOperativa = {
      ...alertaOperativa,
      id: 32,
      tipo: 'puerta',
    }

    const { result } = renderHook(() => useDashboard())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(result.current.alertasActivas).toEqual([alertaOperativa])
    expect(result.current.cargandoAlertas).toBe(false)

    vi.mocked(obtenerAlertasActivas).mockResolvedValueOnce([nueva])
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })

    expect(result.current.alertasActivas).toEqual([nueva])
    expect(result.current.errorAlertas).toBeNull()
  })

  it('conserva las alertas activas si falla el refresco', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() =>
      expect(result.current.alertasActivas).toEqual([alertaOperativa]),
    )

    vi.mocked(obtenerAlertasActivas).mockRejectedValueOnce(new Error('sin red'))

    await act(async () => {
      await result.current.refrescar()
    })

    expect(result.current.alertasActivas).toEqual([alertaOperativa])
    expect(result.current.errorAlertas).toBe('sin red')
    expect(result.current.cargandoAlertas).toBe(false)
    expect(result.current.errorResumen).toBeNull()
  })

  it('expone el error inicial de alertas activas sin tumbar cámaras', async () => {
    vi.mocked(obtenerAlertasActivas).mockRejectedValueOnce(new Error('sin red'))

    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.camaras).toHaveLength(2))
    await waitFor(() => expect(result.current.errorAlertas).toBe('sin red'))

    expect(result.current.alertasActivas).toEqual([])
    expect(result.current.cargandoAlertas).toBe(false)
    expect(result.current.errorResumen).toBeNull()
  })

  it('refresca las alertas activas con alerta_abierta y alerta_cerrada', async () => {
    vi.useFakeTimers()
    const nueva: AlertaOperativa = {
      ...alertaOperativa,
      id: 32,
      tipo: 'puerta',
    }

    const { result } = renderHook(() => useDashboard())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.alertasActivas).toEqual([alertaOperativa])

    vi.mocked(obtenerAlertasActivas).mockResolvedValueOnce([nueva])
    act(() => {
      emitir('alerta_abierta', { id: 32 })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RETRASO_ALERTAS_ACTIVAS_MS)
    })
    expect(result.current.alertasActivas).toEqual([nueva])

    vi.mocked(obtenerAlertasActivas).mockResolvedValueOnce([alertaOperativa])
    act(() => {
      emitir('alerta_cerrada', { id: 31 })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RETRASO_ALERTAS_ACTIVAS_MS)
    })
    expect(result.current.alertasActivas).toEqual([alertaOperativa])
  })

  it('atiende una alerta, marca el estado por id y refresca KPIs', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() =>
      expect(result.current.alertasActivas).toEqual([alertaOperativa]),
    )
    const llamadasKpis = vi.mocked(obtenerKpis).mock.calls.length

    let resolver!: (alerta: AlertaOperativa) => void
    const pendiente = new Promise<AlertaOperativa>((resolve) => {
      resolver = resolve
    })
    vi.mocked(atenderAlertaApi).mockReturnValueOnce(pendiente)

    let atencion!: Promise<void>
    act(() => {
      atencion = result.current.atenderAlerta(31, 'Se cerró la puerta')
    })
    await waitFor(() => expect(result.current.atendiendo[31]).toBe(true))

    await act(async () => {
      resolver({ ...alertaOperativa, atendida_por: 3 })
      await atencion
    })

    expect(atenderAlertaApi).toHaveBeenCalledWith(31, 'Se cerró la puerta')
    expect(result.current.atendiendo[31]).toBeUndefined()
    expect(result.current.alertasActivas[0]).toMatchObject({
      id: 31,
      atendida_por: 3,
    })
    expect(vi.mocked(obtenerKpis).mock.calls.length).toBeGreaterThan(
      llamadasKpis,
    )
  })

  it('refetchea la lista si atender devuelve 409', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() =>
      expect(result.current.alertasActivas).toEqual([alertaOperativa]),
    )

    vi.mocked(atenderAlertaApi).mockRejectedValueOnce(
      new ErrorApi('La alerta ya está cerrada', 409),
    )
    vi.mocked(obtenerAlertasActivas).mockResolvedValueOnce([])

    await act(async () => {
      await result.current.atenderAlerta(31)
    })

    expect(result.current.alertasActivas).toEqual([])
    expect(result.current.errorAlertas).toBeNull()
    expect(result.current.atendiendo[31]).toBeUndefined()
  })

  it('conserva la alerta y expone el error si atender falla', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() =>
      expect(result.current.alertasActivas).toEqual([alertaOperativa]),
    )

    vi.mocked(atenderAlertaApi).mockRejectedValueOnce(new Error('sin red'))

    await act(async () => {
      await result.current.atenderAlerta(31)
    })

    expect(result.current.alertasActivas).toEqual([alertaOperativa])
    expect(result.current.errorAlertas).toBe('sin red')
    expect(result.current.atendiendo[31]).toBeUndefined()
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
    expect(result.current.errorResumen).toBe('sin red')

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

  it('fusiona los puntos SSE que llegan mientras se carga el historial', async () => {
    let resolverHttp!: (lecturas: Lectura[]) => void
    const httpPendiente = new Promise<Lectura[]>((resolver) => {
      resolverHttp = resolver
    })
    vi.mocked(obtenerLecturas).mockImplementation((id) => {
      if (id === 1) {
        return httpPendiente
      }
      return Promise.resolve([crearLectura(id, 3)])
    })

    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.camaras).toHaveLength(2))
    await waitFor(() => expect(obtenerLecturas).toHaveBeenCalledTimes(2))

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

    await act(async () => {
      resolverHttp([
        crearLectura(1, 1, '2026-11-14T10:00:00+00:00'),
        crearLectura(1, 1.1, '2026-11-14T10:01:00+00:00'),
      ])
    })

    await waitFor(() => expect(result.current.series[1]).toEqual([1, 1.1, 4.2]))
  })

  it('pide las series de una cámara nueva en el polling', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.series[2]).toEqual([3]))
    expect(obtenerLecturas).toHaveBeenCalledTimes(2)

    const [, carnes] = crearCamaras()
    const tercera: Camara = { ...carnes, id: 3, nombre: 'Lácteos' }
    vi.mocked(obtenerCamaras).mockResolvedValueOnce([
      ...crearCamaras(),
      tercera,
    ])

    await act(async () => {
      await result.current.refrescar()
    })

    await waitFor(() => expect(result.current.series[3]).toEqual([4]))
    expect(obtenerLecturas).toHaveBeenCalledTimes(3)
  })

  it('vuelve a pedir las series al reconectar el SSE', async () => {
    const { result, rerender } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.series[1]).toEqual([2]))
    expect(obtenerLecturas).toHaveBeenCalledTimes(2)

    vi.mocked(useStreamReconexion).mockReturnValue(1)
    rerender()

    await waitFor(() => expect(obtenerLecturas).toHaveBeenCalledTimes(4))
  })

  it('no cancela un refresco completo con un evento de alerta', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.camaras).toHaveLength(2))

    let resolver!: (camaras: Camara[]) => void
    const pendiente = new Promise<Camara[]>((resolve) => {
      resolver = resolve
    })
    vi.mocked(obtenerCamaras).mockImplementationOnce(() => pendiente)

    let refresco!: Promise<void>
    act(() => {
      refresco = result.current.refrescar()
    })
    await waitFor(() => expect(obtenerCamaras).toHaveBeenCalledTimes(2))

    vi.useFakeTimers()
    act(() => {
      emitir('alerta_abierta', { id: 1 })
    })
    await act(async () => {
      vi.advanceTimersByTime(500)
    })

    expect(obtenerCamaras).toHaveBeenCalledTimes(2)

    await act(async () => {
      resolver(crearCamaras())
      await refresco
    })
  })

  it('no pierde /health si arranca un refresco por evento', async () => {
    vi.useFakeTimers()
    let resolverSalud!: (salud: Health) => void
    const saludPendiente = new Promise<Health>((resolve) => {
      resolverSalud = resolve
    })
    vi.mocked(obtenerHealth).mockReturnValueOnce(saludPendiente)

    const { result } = renderHook(() => useDashboard())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(result.current.camaras).toHaveLength(2)
    expect(result.current.health).toBeNull()

    act(() => {
      emitir('alerta_abierta', { id: 1 })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
      await Promise.resolve()
    })

    await act(async () => {
      resolverSalud({ ok: true, escala_tiempo: 30 })
    })

    expect(result.current.health).toEqual({ ok: true, escala_tiempo: 30 })
  })

  it('mantiene el error de resumen aunque el SSE siga enviando datos', async () => {
    const { result } = renderHook(() => useDashboard())
    await waitFor(() => expect(result.current.camaras).toHaveLength(2))

    vi.mocked(obtenerKpis).mockRejectedValueOnce(new Error('kpis caído'))
    await act(async () => {
      await result.current.refrescar()
    })
    expect(result.current.errorResumen).toBe('kpis caído')

    act(() => {
      emitir('kpis', { ...kpis, alertas_activas: 4 })
    })

    expect(result.current.ultimaActividadSse).toBeInstanceOf(Date)
    expect(result.current.errorResumen).toBe('kpis caído')
    expect(result.current.kpis?.alertas_activas).toBe(4)
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
    expect(result.current.errorResumen).toBeNull()
    expect(result.current.cargando).toBe(false)
  })

  it('expone el error inicial y refrescar lo limpia al reintentar', async () => {
    vi.mocked(obtenerCamaras).mockRejectedValueOnce(
      new Error('La API no responde'),
    )

    const { result } = renderHook(() => useDashboard())

    await waitFor(() =>
      expect(result.current.errorResumen).toBe('La API no responde'),
    )
    expect(result.current.cargando).toBe(false)
    expect(result.current.camaras).toEqual([])
    expect(obtenerLecturas).not.toHaveBeenCalled()

    await act(async () => {
      await result.current.refrescar()
    })

    expect(result.current.errorResumen).toBeNull()
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

    expect(result.current.errorResumen).toBe('sin red')
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
    const anterior = result.current.ultimaActividadSse

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
    expect(result.current.ultimaActividadSse).not.toBe(anterior)
    expect(result.current.ultimaActividadSse).toBeInstanceOf(Date)
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

describe('fusionarSeries', () => {
  const punto = (ts: string, valor: number): PuntoSerie => ({ ts, valor })

  it('mezcla el HTTP con los puntos SSE posteriores y deduplica por ts', () => {
    const http = {
      1: [punto('2026-11-14T10:00:00Z', 1), punto('2026-11-14T10:01:00Z', 1.1)],
    }
    const actuales = {
      1: [
        punto('2026-11-14T10:00:00Z', 0.9),
        punto('2026-11-14T10:05:00Z', 4.2),
      ],
    }

    expect(fusionarSeries(actuales, http)[1]).toEqual([
      punto('2026-11-14T10:00:00Z', 1),
      punto('2026-11-14T10:01:00Z', 1.1),
      punto('2026-11-14T10:05:00Z', 4.2),
    ])
  })

  it('conserva los puntos actuales si el HTTP no trae historial', () => {
    const actuales = { 1: [punto('2026-11-14T10:05:00Z', 4.2)] }

    expect(fusionarSeries(actuales, { 1: [] })[1]).toEqual(actuales[1])
  })

  it('recorta el resultado al tope de puntos', () => {
    const http = {
      1: Array.from({ length: MAX_PUNTOS_SERIE + 5 }, (_, indice) =>
        punto(`2026-11-14T10:${String(indice).padStart(2, '0')}:00Z`, indice),
      ),
    }

    const resultado = fusionarSeries({}, http)[1]

    expect(resultado).toHaveLength(MAX_PUNTOS_SERIE)
    expect(resultado.at(-1)?.valor).toBe(MAX_PUNTOS_SERIE + 4)
  })
})
