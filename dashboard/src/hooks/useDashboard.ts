import { useCallback, useEffect, useRef, useState } from 'react'
import {
  obtenerAlertasSeguridad,
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
} from '../api/client'
import { esObjeto, parsearJson } from '../lib/sse'
import { useStreamEvent } from '../realtime/StreamProvider'
import type {
  AlertaSeguridad,
  Camara,
  EstadoCamara,
  Health,
  Kpis,
  LecturaStream,
  SerieCamara,
} from '../types'

/** Respaldo por si el SSE se cae: vuelve a preguntar cámaras y KPIs. */
export const INTERVALO_REFRESCO_MS = 60_000
/** Debounce de los eventos que no traen el valor en riesgo actualizado. */
export const RETRASO_RESUMEN_MS = 500
/** Puntos iniciales del sparkline (las últimas 30 temperaturas de 2 h). */
export const PUNTOS_INICIALES = 30
/** Tope de la serie en vivo para no crecer sin límite entre refrescos. */
export const MAX_PUNTOS_SERIE = 40

export interface EstadoDashboard {
  health: Health | null
  camaras: Camara[]
  kpis: Kpis | null
  /** Alertas del detector SIEM; se actualizan con el polling de 60 s. */
  alertasSeguridad: AlertaSeguridad[]
  /** Temperaturas por cámara, de la más vieja a la más reciente. */
  series: Record<number, SerieCamara>
  /** Solo la primera carga (o un reintento sin datos) marca `true`. */
  cargando: boolean
  error: string | null
  actualizadoEn: Date | null
  refrescar: () => Promise<void>
}

/**
 * Une la carga inicial de la API, el respaldo por polling y el stream SSE.
 * `StreamProvider` reparte los eventos; aquí solo se interpretan.
 *
 * Cada solicitud HTTP aborta la anterior y lleva un id: una respuesta vieja
 * que resuelve tarde no puede pisar a la más reciente ni a un evento SSE.
 */
export function useDashboard(): EstadoDashboard {
  const [health, setHealth] = useState<Health | null>(null)
  const [camaras, setCamaras] = useState<Camara[]>([])
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [alertasSeguridad, setAlertasSeguridad] = useState<AlertaSeguridad[]>(
    [],
  )
  const [series, setSeries] = useState<Record<number, SerieCamara>>({})
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actualizadoEn, setActualizadoEn] = useState<Date | null>(null)

  const activoRef = useRef(false)
  const hayDatosRef = useRef(false)
  const seriesCargadasRef = useRef(false)
  const healthRef = useRef<Health | null>(null)
  const healthIntentadoRef = useRef(false)
  const controladorRef = useRef<AbortController | null>(null)
  const solicitudRef = useRef(0)
  const timerResumenRef = useRef<number | null>(null)

  const iniciarSolicitud = useCallback(() => {
    controladorRef.current?.abort()
    const controlador = new AbortController()
    controladorRef.current = controlador
    solicitudRef.current += 1
    return { id: solicitudRef.current, signal: controlador.signal }
  }, [])

  /**
   * `manual` permite reintentar `/health` si la carga inicial no lo obtuvo.
   * El polling no lo repite: `escala_tiempo` es estático.
   */
  const ejecutarRefresco = useCallback(
    async (manual: boolean) => {
      const { id, signal } = iniciarSolicitud()
      const primera = !hayDatosRef.current
      const incluirSeries = !seriesCargadasRef.current
      const pedirHealth =
        healthRef.current === null && (manual || !healthIntentadoRef.current)

      if (pedirHealth) {
        healthIntentadoRef.current = true
        // `/health` solo controla la etiqueta de demo: si falla o tarda, las
        // cámaras y los KPIs se muestran igual.
        void obtenerHealth(signal)
          .then((salud) => {
            if (!activoRef.current || solicitudRef.current !== id) {
              return
            }
            healthRef.current = salud
            setHealth(salud)
          })
          .catch(() => {
            // Opcional para el dashboard; se reintenta en un refresco manual.
          })
      }

      try {
        const [lista, kpisNuevos, alertas] = await Promise.all([
          obtenerCamaras(signal),
          obtenerKpis(signal),
          // Seguridad es opcional: si falla se conservan las alertas previas.
          obtenerAlertasSeguridad(signal).catch(() => null),
        ])
        if (!activoRef.current || solicitudRef.current !== id) {
          return
        }

        setCamaras((actuales) => fusionarCamaras(actuales, lista))
        setKpis(kpisNuevos)
        if (alertas) {
          setAlertasSeguridad(alertas)
        }
        setActualizadoEn(new Date())
        setError(null)
        hayDatosRef.current = true
        if (primera) {
          setCargando(false)
        }

        if (incluirSeries) {
          const seriesNuevas = await cargarSeries(lista, signal)
          if (!activoRef.current || solicitudRef.current !== id) {
            return
          }
          setSeries(seriesNuevas)
          seriesCargadasRef.current = true
        }
      } catch (fallo) {
        if (!activoRef.current || solicitudRef.current !== id) {
          return
        }
        if (esAbortado(fallo)) {
          return
        }
        setError(mensajeDeError(fallo))
      } finally {
        if (activoRef.current && solicitudRef.current === id && primera) {
          setCargando(false)
        }
      }
    },
    [iniciarSolicitud],
  )

  const refrescarResumen = useCallback(async () => {
    const { id, signal } = iniciarSolicitud()

    try {
      const [lista, kpisNuevos] = await Promise.all([
        obtenerCamaras(signal),
        obtenerKpis(signal),
      ])
      if (!activoRef.current || solicitudRef.current !== id) {
        return
      }

      const primera = !hayDatosRef.current
      setCamaras((actuales) => fusionarCamaras(actuales, lista))
      setKpis(kpisNuevos)
      setActualizadoEn(new Date())
      setError(null)
      hayDatosRef.current = true
      if (primera) {
        setCargando(false)
      }
    } catch (fallo) {
      if (!activoRef.current || solicitudRef.current !== id) {
        return
      }
      if (!hayDatosRef.current) {
        setCargando(false)
      }
      if (esAbortado(fallo)) {
        return
      }
      setError(mensajeDeError(fallo))
    }
  }, [iniciarSolicitud])

  const programarRefrescoResumen = useCallback(() => {
    if (timerResumenRef.current !== null) {
      window.clearTimeout(timerResumenRef.current)
    }
    timerResumenRef.current = window.setTimeout(() => {
      timerResumenRef.current = null
      void refrescarResumen()
    }, RETRASO_RESUMEN_MS)
  }, [refrescarResumen])

  useEffect(() => {
    activoRef.current = true
    // La carga debe arrancar al montar; los setState de `ejecutarRefresco`
    // ocurren después del primer await, cuando ya hay respuesta de la API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void ejecutarRefresco(true)
    const intervalo = window.setInterval(() => {
      void ejecutarRefresco(false)
    }, INTERVALO_REFRESCO_MS)

    return () => {
      activoRef.current = false
      controladorRef.current?.abort()
      window.clearInterval(intervalo)
      if (timerResumenRef.current !== null) {
        window.clearTimeout(timerResumenRef.current)
        timerResumenRef.current = null
      }
    }
  }, [ejecutarRefresco])

  const alRecibirLectura = useCallback((evento: MessageEvent<string>) => {
    const lectura = leerLectura(evento.data)
    if (!lectura) {
      return
    }

    setCamaras((actual) =>
      actual.map((camara) =>
        camara.id === lectura.camara_id
          ? {
              ...camara,
              estado: lectura.estado_camara,
              ultima_lectura: {
                ts: lectura.ts,
                temperatura_c: lectura.temperatura_c,
                humedad_pct: lectura.humedad_pct,
                puerta_abierta: lectura.puerta_abierta,
              },
            }
          : camara,
      ),
    )

    setSeries((actual) => {
      const serie = actual[lectura.camara_id] ?? []
      return {
        ...actual,
        [lectura.camara_id]: [...serie, lectura.temperatura_c].slice(
          -MAX_PUNTOS_SERIE,
        ),
      }
    })

    setActualizadoEn(new Date())
  }, [])

  const alRecibirKpis = useCallback((evento: MessageEvent<string>) => {
    const nuevos = leerKpis(evento.data)
    if (nuevos) {
      setKpis(nuevos)
      setActualizadoEn(new Date())
    }
  }, [])

  useStreamEvent('lectura', alRecibirLectura)
  useStreamEvent('kpis', alRecibirKpis)
  useStreamEvent('alerta_abierta', programarRefrescoResumen)
  useStreamEvent('alerta_cerrada', programarRefrescoResumen)
  useStreamEvent('lote_actualizado', programarRefrescoResumen)

  const refrescar = useCallback(async () => {
    if (!hayDatosRef.current) {
      setCargando(true)
    }
    await ejecutarRefresco(true)
  }, [ejecutarRefresco])

  return {
    health,
    camaras,
    kpis,
    alertasSeguridad,
    series,
    cargando,
    error,
    actualizadoEn,
    refrescar,
  }
}

/**
 * Conserva la lectura y el estado más nuevos cuando el SSE adelantó al HTTP.
 * `valor_en_riesgo_mxn` siempre viene de la API: es el resumen autoritativo
 * después de alertas y cambios de lote.
 */
export function fusionarCamaras(
  actuales: Camara[],
  nuevas: Camara[],
): Camara[] {
  const porId = new Map(actuales.map((camara) => [camara.id, camara]))

  return nuevas.map((nueva) => {
    const actual = porId.get(nueva.id)
    const lecturaActual = actual?.ultima_lectura
    if (!actual || !lecturaActual) {
      return nueva
    }

    const lecturaNueva = nueva.ultima_lectura
    const actualEsMasNueva =
      !lecturaNueva ||
      new Date(lecturaActual.ts).getTime() > new Date(lecturaNueva.ts).getTime()

    if (!actualEsMasNueva) {
      return nueva
    }

    return {
      ...nueva,
      estado: actual.estado,
      ultima_lectura: lecturaActual,
    }
  })
}

/** Una serie fallida no tumba la carga: esa cámara queda sin sparkline. */
async function cargarSeries(
  camaras: Camara[],
  signal: AbortSignal,
): Promise<Record<number, SerieCamara>> {
  const resultados = await Promise.allSettled(
    camaras.map((camara) => obtenerLecturas(camara.id, signal)),
  )
  const series: Record<number, SerieCamara> = {}

  resultados.forEach((resultado, indice) => {
    if (resultado.status !== 'fulfilled') {
      return
    }
    series[camaras[indice].id] = resultado.value
      .slice(-PUNTOS_INICIALES)
      .map((lectura) => lectura.temperatura_c)
  })

  return series
}

function esAbortado(fallo: unknown): boolean {
  return (
    typeof fallo === 'object' &&
    fallo !== null &&
    'name' in fallo &&
    fallo.name === 'AbortError'
  )
}

function mensajeDeError(fallo: unknown): string {
  if (fallo instanceof Error && fallo.message) {
    return fallo.message
  }
  return 'No se pudo conectar con la API de FríoTrack.'
}

function esEstado(valor: unknown): valor is EstadoCamara {
  return valor === 'en_rango' || valor === 'alerta' || valor === 'critica'
}

function leerLectura(texto: string): LecturaStream | null {
  const datos = parsearJson(texto)
  if (!esObjeto(datos)) {
    return null
  }

  const {
    camara_id: camaraId,
    ts,
    temperatura_c: temperatura,
    humedad_pct: humedad,
    puerta_abierta: puertaAbierta,
    estado_camara: estado,
  } = datos

  if (
    typeof camaraId !== 'number' ||
    typeof ts !== 'string' ||
    typeof temperatura !== 'number' ||
    typeof humedad !== 'number' ||
    typeof puertaAbierta !== 'boolean' ||
    !esEstado(estado)
  ) {
    return null
  }

  return {
    camara_id: camaraId,
    ts,
    temperatura_c: temperatura,
    humedad_pct: humedad,
    puerta_abierta: puertaAbierta,
    estado_camara: estado,
  }
}

const CAMPOS_KPIS = [
  'pct_tiempo_en_rango_24h',
  'alertas_activas',
  'tiempo_respuesta_promedio_min',
  'valor_en_riesgo_mxn',
  'merma_hoy_mxn',
  'merma_mes_mxn',
] as const

function esKpis(valor: unknown): valor is Kpis {
  if (!esObjeto(valor)) {
    return false
  }
  return CAMPOS_KPIS.every((campo) => typeof valor[campo] === 'number')
}

function leerKpis(texto: string): Kpis | null {
  const datos = parsearJson(texto)
  return esKpis(datos) ? datos : null
}
