import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  obtenerAlertasSeguridad,
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
} from '../api/client'
import { parsearJson } from '../lib/sse'
import { esObjeto } from '../lib/validacion'
import { useStreamEvent, useStreamReconexion } from '../realtime/StreamProvider'
import type {
  AlertaSeguridad,
  Camara,
  EstadoCamara,
  Health,
  Kpis,
  LecturaStream,
  PuntoSerie,
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
  /** Alertas del detector SIEM, en su propio carril. */
  alertasSeguridad: AlertaSeguridad[]
  /** `true` cuando la última carga de alertas terminó bien. */
  alertasCargadas: boolean
  /** Fallo del carril de alertas; no afecta cámaras ni KPIs. */
  errorAlertas: string | null
  /** Temperaturas por cámara, de la más vieja a la más reciente. */
  series: Record<number, SerieCamara>
  /** Solo la primera carga (o un reintento sin datos) marca `true`. */
  cargando: boolean
  /** Fallo del resumen HTTP (`/camaras` o `/kpis`), no del SSE. */
  errorResumen: string | null
  /** Último resumen HTTP exitoso. */
  ultimoExitoHttp: Date | null
  /** Último evento SSE recibido en este hook. */
  ultimaActividadSse: Date | null
  refrescar: () => Promise<void>
}

/**
 * Une la carga inicial de la API, el respaldo por polling y el stream SSE.
 *
 * Cada carril (resumen, series, health y alertas) tiene su propio
 * `AbortController` e id: un evento de alerta no cancela el polling, una
 * respuesta lenta de seguridad no bloquea cámaras/KPIs y una respuesta vieja
 * no pisa a otra más reciente.
 */
export function useDashboard(): EstadoDashboard {
  const [health, setHealth] = useState<Health | null>(null)
  const [camaras, setCamaras] = useState<Camara[]>([])
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [alertasSeguridad, setAlertasSeguridad] = useState<AlertaSeguridad[]>(
    [],
  )
  const [alertasCargadas, setAlertasCargadas] = useState(false)
  const [errorAlertas, setErrorAlertas] = useState<string | null>(null)
  const [puntosSeries, setPuntosSeries] = useState<
    Record<number, PuntoSerie[]>
  >({})
  const [cargando, setCargando] = useState(true)
  const [errorResumen, setErrorResumen] = useState<string | null>(null)
  const [ultimoExitoHttp, setUltimoExitoHttp] = useState<Date | null>(null)
  const [ultimaActividadSse, setUltimaActividadSse] = useState<Date | null>(
    null,
  )

  const activoRef = useRef(false)
  const hayDatosRef = useRef(false)

  // Carril del resumen completo: /camaras + /kpis.
  const resumenControladorRef = useRef<AbortController | null>(null)
  const resumenSolicitudRef = useRef(0)
  const resumenEnVueloRef = useRef(false)

  // Carril de los refrescos disparados por SSE (alerta_* / lote_*).
  const resumenEventoControladorRef = useRef<AbortController | null>(null)
  const resumenEventoSolicitudRef = useRef(0)
  const resumenEventoEnVueloRef = useRef(false)

  // Versión compartida por ambos carriles de resumen: gana la más reciente.
  const versionResumenRef = useRef(0)

  // Carril de series: historial y huecos.
  const seriesControladorRef = useRef<AbortController | null>(null)
  const seriesSolicitudRef = useRef(0)
  const seriesEnVueloRef = useRef(false)
  const seriesPendientesRef = useRef<Set<number>>(new Set())
  const seriesRef = useRef<Record<number, PuntoSerie[]>>({})

  // Carril de health: estático, independiente de los refrescos.
  const healthControladorRef = useRef<AbortController | null>(null)
  const healthSolicitudRef = useRef(0)
  const healthRef = useRef<Health | null>(null)

  // Carril de alertas: no comparte señal ni orden con cámaras/KPIs.
  const alertasControladorRef = useRef<AbortController | null>(null)
  const alertasSolicitudRef = useRef(0)

  const timerResumenRef = useRef<number | null>(null)

  const actualizarPuntos = useCallback(
    (
      calculo: (
        actual: Record<number, PuntoSerie[]>,
      ) => Record<number, PuntoSerie[]>,
    ) => {
      const siguiente = calculo(seriesRef.current)
      seriesRef.current = siguiente
      setPuntosSeries(siguiente)
    },
    [],
  )

  const cargarSeries = useCallback(
    async (ids: number[]) => {
      if (!activoRef.current) {
        return
      }
      for (const id of ids) {
        seriesPendientesRef.current.add(id)
      }
      if (seriesEnVueloRef.current) {
        return
      }

      seriesEnVueloRef.current = true
      try {
        while (seriesPendientesRef.current.size > 0 && activoRef.current) {
          const lote = [...seriesPendientesRef.current]
          seriesPendientesRef.current.clear()

          seriesControladorRef.current?.abort()
          const controlador = new AbortController()
          seriesControladorRef.current = controlador
          seriesSolicitudRef.current += 1
          const idSolicitud = seriesSolicitudRef.current

          const resultados = await Promise.allSettled(
            lote.map((id) => obtenerLecturas(id, controlador.signal)),
          )
          if (
            !activoRef.current ||
            seriesSolicitudRef.current !== idSolicitud
          ) {
            return
          }

          const http: Record<number, PuntoSerie[]> = {}
          resultados.forEach((resultado, indice) => {
            if (resultado.status !== 'fulfilled') {
              return
            }
            http[lote[indice]] = resultado.value
              .slice(-PUNTOS_INICIALES)
              .map((lectura) => ({
                ts: lectura.ts,
                valor: lectura.temperatura_c,
              }))
          })

          actualizarPuntos((actual) => fusionarSeries(actual, http))
        }
      } finally {
        seriesEnVueloRef.current = false
      }
    },
    [actualizarPuntos],
  )

  const cargarHealth = useCallback(async () => {
    if (!activoRef.current || healthRef.current !== null) {
      return
    }

    healthControladorRef.current?.abort()
    const controlador = new AbortController()
    healthControladorRef.current = controlador
    healthSolicitudRef.current += 1
    const idSolicitud = healthSolicitudRef.current

    try {
      const salud = await obtenerHealth(controlador.signal)
      if (!activoRef.current || healthSolicitudRef.current !== idSolicitud) {
        return
      }
      healthRef.current = salud
      setHealth(salud)
    } catch {
      // Es opcional: solo controla la etiqueta de demo.
    }
  }, [])

  const cargarAlertas = useCallback(async () => {
    alertasControladorRef.current?.abort()
    const controlador = new AbortController()
    alertasControladorRef.current = controlador
    alertasSolicitudRef.current += 1
    const idSolicitud = alertasSolicitudRef.current

    try {
      const alertas = await obtenerAlertasSeguridad(controlador.signal)
      if (!activoRef.current || alertasSolicitudRef.current !== idSolicitud) {
        return
      }
      setAlertasSeguridad(alertas)
      setAlertasCargadas(true)
      setErrorAlertas(null)
    } catch (fallo) {
      if (
        !activoRef.current ||
        alertasSolicitudRef.current !== idSolicitud ||
        esAbortado(fallo)
      ) {
        return
      }
      // Se conservan las alertas previas; el panel muestra el estado de error.
      setErrorAlertas(mensajeDeError(fallo))
    }
  }, [])

  const aplicarResumen = useCallback(
    (version: number, lista: Camara[], kpisNuevos: Kpis) => {
      if (!activoRef.current || version !== versionResumenRef.current) {
        return
      }

      const primera = !hayDatosRef.current
      setCamaras((actuales) => fusionarCamaras(actuales, lista))
      setKpis(kpisNuevos)
      setUltimoExitoHttp(new Date())
      setErrorResumen(null)
      hayDatosRef.current = true
      if (primera) {
        setCargando(false)
      }

      // Una cámara nueva en el polling se queda sin historial hasta que se
      // pide su serie; las que ya tienen puntos no se vuelven a descargar.
      const faltantes = lista
        .map((camara) => camara.id)
        .filter((id) => seriesRef.current[id] === undefined)
      if (faltantes.length > 0) {
        void cargarSeries(faltantes)
      }
    },
    [cargarSeries],
  )

  const cargarResumen = useCallback(async () => {
    resumenControladorRef.current?.abort()
    const controlador = new AbortController()
    resumenControladorRef.current = controlador
    resumenSolicitudRef.current += 1
    const idSolicitud = resumenSolicitudRef.current
    versionResumenRef.current += 1
    const version = versionResumenRef.current
    resumenEnVueloRef.current = true

    try {
      const [lista, kpisNuevos] = await Promise.all([
        obtenerCamaras(controlador.signal),
        obtenerKpis(controlador.signal),
      ])
      if (
        !activoRef.current ||
        resumenSolicitudRef.current !== idSolicitud ||
        versionResumenRef.current !== version
      ) {
        return
      }
      aplicarResumen(version, lista, kpisNuevos)
    } catch (fallo) {
      if (
        !activoRef.current ||
        resumenSolicitudRef.current !== idSolicitud ||
        versionResumenRef.current !== version ||
        esAbortado(fallo)
      ) {
        return
      }
      setErrorResumen(mensajeDeError(fallo))
      if (!hayDatosRef.current) {
        setCargando(false)
      }
    } finally {
      if (resumenSolicitudRef.current === idSolicitud) {
        resumenEnVueloRef.current = false
      }
    }
  }, [aplicarResumen])

  const cargarResumenPorEvento = useCallback(async () => {
    // Un refresco completo ya trae datos más nuevos; no lo cancelamos.
    if (resumenEnVueloRef.current || resumenEventoEnVueloRef.current) {
      return
    }

    const controlador = new AbortController()
    resumenEventoControladorRef.current = controlador
    resumenEventoSolicitudRef.current += 1
    const idSolicitud = resumenEventoSolicitudRef.current
    versionResumenRef.current += 1
    const version = versionResumenRef.current
    resumenEventoEnVueloRef.current = true

    try {
      const [lista, kpisNuevos] = await Promise.all([
        obtenerCamaras(controlador.signal),
        obtenerKpis(controlador.signal),
      ])
      if (
        !activoRef.current ||
        resumenEventoSolicitudRef.current !== idSolicitud ||
        versionResumenRef.current !== version
      ) {
        return
      }
      aplicarResumen(version, lista, kpisNuevos)
    } catch (fallo) {
      if (
        !activoRef.current ||
        resumenEventoSolicitudRef.current !== idSolicitud ||
        versionResumenRef.current !== version ||
        esAbortado(fallo)
      ) {
        return
      }
      setErrorResumen(mensajeDeError(fallo))
      if (!hayDatosRef.current) {
        setCargando(false)
      }
    } finally {
      if (resumenEventoSolicitudRef.current === idSolicitud) {
        resumenEventoEnVueloRef.current = false
      }
    }
  }, [aplicarResumen])

  const programarRefrescoResumen = useCallback(() => {
    if (timerResumenRef.current !== null) {
      window.clearTimeout(timerResumenRef.current)
    }
    timerResumenRef.current = window.setTimeout(() => {
      timerResumenRef.current = null
      void cargarResumenPorEvento()
    }, RETRASO_RESUMEN_MS)
  }, [cargarResumenPorEvento])

  useEffect(() => {
    activoRef.current = true
    // La carga arranca al montar; los setState ocurren después del primer
    // await, cuando ya hay respuesta de la API.
    void cargarResumen()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void cargarHealth()
    void cargarAlertas()

    const intervaloResumen = window.setInterval(() => {
      void cargarResumen()
    }, INTERVALO_REFRESCO_MS)
    const intervaloAlertas = window.setInterval(() => {
      void cargarAlertas()
    }, INTERVALO_REFRESCO_MS)

    return () => {
      activoRef.current = false
      resumenControladorRef.current?.abort()
      resumenEventoControladorRef.current?.abort()
      seriesControladorRef.current?.abort()
      healthControladorRef.current?.abort()
      alertasControladorRef.current?.abort()
      window.clearInterval(intervaloResumen)
      window.clearInterval(intervaloAlertas)
      if (timerResumenRef.current !== null) {
        window.clearTimeout(timerResumenRef.current)
        timerResumenRef.current = null
      }
    }
  }, [cargarResumen, cargarHealth, cargarAlertas])

  const reconexiones = useStreamReconexion()
  const reconexionesPreviasRef = useRef(reconexiones)

  useEffect(() => {
    if (reconexiones === reconexionesPreviasRef.current) {
      return
    }
    reconexionesPreviasRef.current = reconexiones
    if (camaras.length > 0) {
      // Rellena el hueco que dejó la caída del SSE con el historial HTTP.
      void cargarSeries(camaras.map((camara) => camara.id))
    }
  }, [reconexiones, camaras, cargarSeries])

  const alRecibirLectura = useCallback(
    (evento: MessageEvent<string>) => {
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

      actualizarPuntos((actual) => {
        const puntos = actual[lectura.camara_id] ?? []
        const sinDuplicado = puntos.filter((punto) => punto.ts !== lectura.ts)
        return {
          ...actual,
          [lectura.camara_id]: [
            ...sinDuplicado,
            { ts: lectura.ts, valor: lectura.temperatura_c },
          ].slice(-MAX_PUNTOS_SERIE),
        }
      })

      setUltimaActividadSse(new Date())
    },
    [actualizarPuntos],
  )

  const alRecibirKpis = useCallback((evento: MessageEvent<string>) => {
    const nuevos = leerKpis(evento.data)
    if (nuevos) {
      setKpis(nuevos)
      setUltimaActividadSse(new Date())
    }
  }, [])

  const alRecibirEventoResumen = useCallback(() => {
    setUltimaActividadSse(new Date())
    programarRefrescoResumen()
  }, [programarRefrescoResumen])

  useStreamEvent('lectura', alRecibirLectura)
  useStreamEvent('kpis', alRecibirKpis)
  useStreamEvent('alerta_abierta', alRecibirEventoResumen)
  useStreamEvent('alerta_cerrada', alRecibirEventoResumen)
  useStreamEvent('lote_actualizado', alRecibirEventoResumen)

  const refrescar = useCallback(async () => {
    if (!hayDatosRef.current) {
      setCargando(true)
    }
    await Promise.all([cargarResumen(), cargarHealth(), cargarAlertas()])
  }, [cargarResumen, cargarHealth, cargarAlertas])

  const series = useMemo(() => {
    const resultado: Record<number, SerieCamara> = {}
    for (const [idTexto, puntos] of Object.entries(puntosSeries)) {
      resultado[Number(idTexto)] = puntos.map((punto) => punto.valor)
    }
    return resultado
  }, [puntosSeries])

  return {
    health,
    camaras,
    kpis,
    alertasSeguridad,
    alertasCargadas,
    errorAlertas,
    series,
    cargando,
    errorResumen,
    ultimoExitoHttp,
    ultimaActividadSse,
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

/**
 * Fusiona el historial HTTP con los puntos SSE que llegaron mientras la
 * petición estaba en vuelo. Solo conserva del estado actual lo posterior al
 * último punto HTTP y deduplica por `ts`.
 */
export function fusionarSeries(
  actuales: Record<number, PuntoSerie[]>,
  http: Record<number, PuntoSerie[]>,
): Record<number, PuntoSerie[]> {
  const siguiente = { ...actuales }

  for (const [idTexto, puntosHttp] of Object.entries(http)) {
    const id = Number(idTexto)
    const ultimoHttp = puntosHttp.at(-1)?.ts
    const enVivo = actuales[id] ?? []
    const posteriores = ultimoHttp
      ? enVivo.filter((punto) => Date.parse(punto.ts) > Date.parse(ultimoHttp))
      : enVivo

    const porTs = new Map<string, PuntoSerie>()
    for (const punto of puntosHttp) {
      porTs.set(punto.ts, punto)
    }
    for (const punto of posteriores) {
      porTs.set(punto.ts, punto)
    }

    siguiente[id] = [...porTs.values()]
      .sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts))
      .slice(-MAX_PUNTOS_SERIE)
  }

  return siguiente
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
