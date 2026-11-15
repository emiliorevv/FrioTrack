import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import { parsearJson } from '../lib/sse'
import { esObjeto } from '../lib/validacion'
import { useStreamEvent, useStreamReconexion } from '../realtime/StreamProvider'
import type {
  AlertaOperativa,
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
/** Debounce corto de los eventos que cambian las alertas activas. */
export const RETRASO_ALERTAS_ACTIVAS_MS = 300
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
  /** `true` cuando la última carga de alertas de seguridad terminó bien. */
  alertasCargadas: boolean
  /** Fallo del carril de alertas de seguridad; no afecta cámaras ni KPIs. */
  errorAlertasSeguridad: string | null
  /** Alertas operativas que siguen abiertas. */
  alertasActivas: AlertaOperativa[]
  /** `true` mientras no termina la primera carga de alertas activas. */
  cargandoAlertas: boolean
  /** Fallo del carril de alertas activas; no bloquea el resto. */
  errorAlertas: string | null
  /** Fallo de la acción de atender; conserva el `detail` del backend. */
  errorAtender: string | null
  /** Limpia el error de la última acción de atender. */
  limpiarErrorAtender: () => void
  /** Ids con una petición de atención en curso. */
  atendiendo: Record<number, boolean>
  /** Marca una alerta como atendida; el resumen se refresca por SSE/polling. */
  atenderAlerta: (id: number, nota?: string) => Promise<void>
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

interface RefActual<T> {
  current: T
}

/**
 * Ejecutor común de un carril HTTP: aborta el anterior, incrementa el id,
 * comprueba que el componente siga montado y que la respuesta siga vigente,
 * y delega el éxito o el error al llamador.
 */
function useCarril(
  activoRef: RefActual<boolean>,
  controladorRef: RefActual<AbortController | null>,
  solicitudRef: RefActual<number>,
) {
  return useCallback(
    async <T>(
      pedir: (senal: AbortSignal) => Promise<T>,
      aplicar: (datos: T) => void,
      alFallar: (mensaje: string) => void,
    ) => {
      if (!activoRef.current) {
        return
      }

      controladorRef.current?.abort()
      const controlador = new AbortController()
      controladorRef.current = controlador
      solicitudRef.current += 1
      const idSolicitud = solicitudRef.current

      try {
        const datos = await pedir(controlador.signal)
        if (!activoRef.current || solicitudRef.current !== idSolicitud) {
          return
        }
        aplicar(datos)
      } catch (fallo) {
        if (
          !activoRef.current ||
          solicitudRef.current !== idSolicitud ||
          esAbortado(fallo)
        ) {
          return
        }
        alFallar(mensajeDeError(fallo))
      }
    },
    [activoRef, controladorRef, solicitudRef],
  )
}

/**
 * Une la carga inicial de la API, el respaldo por polling y el stream SSE.
 *
 * Cada carril (resumen, series, health, alertas de seguridad y alertas
 * activas) tiene su propio `AbortController` e id: un evento de alerta no
 * cancela el polling, una respuesta lenta de seguridad no bloquea
 * cámaras/KPIs y una respuesta vieja no pisa a otra más reciente.
 */
export function useDashboard(): EstadoDashboard {
  const [health, setHealth] = useState<Health | null>(null)
  const [camaras, setCamaras] = useState<Camara[]>([])
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [alertasSeguridad, setAlertasSeguridad] = useState<AlertaSeguridad[]>(
    [],
  )
  const [alertasCargadas, setAlertasCargadas] = useState(false)
  const [errorAlertasSeguridad, setErrorAlertasSeguridad] = useState<
    string | null
  >(null)
  const [alertasActivas, setAlertasActivas] = useState<AlertaOperativa[]>([])
  const [cargandoAlertas, setCargandoAlertas] = useState(true)
  const [errorAlertas, setErrorAlertas] = useState<string | null>(null)
  const [errorAtender, setErrorAtender] = useState<string | null>(null)
  const [atendiendo, setAtendiendo] = useState<Record<number, boolean>>({})
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

  // Carril de alertas de seguridad: no comparte señal ni orden con el resto.
  const alertasControladorRef = useRef<AbortController | null>(null)
  const alertasSolicitudRef = useRef(0)

  // Carril de alertas operativas activas.
  const alertasActivasControladorRef = useRef<AbortController | null>(null)
  const alertasActivasSolicitudRef = useRef(0)
  const timerAlertasActivasRef = useRef<number | null>(null)
  const atendiendoRef = useRef<Set<number>>(new Set())

  const timerResumenRef = useRef<number | null>(null)

  const ejecutarSeries = useCarril(
    activoRef,
    seriesControladorRef,
    seriesSolicitudRef,
  )
  const ejecutarHealth = useCarril(
    activoRef,
    healthControladorRef,
    healthSolicitudRef,
  )
  const ejecutarAlertasSeguridad = useCarril(
    activoRef,
    alertasControladorRef,
    alertasSolicitudRef,
  )
  const ejecutarAlertasActivas = useCarril(
    activoRef,
    alertasActivasControladorRef,
    alertasActivasSolicitudRef,
  )

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

          await ejecutarSeries(
            (senal) =>
              Promise.allSettled(lote.map((id) => obtenerLecturas(id, senal))),
            (resultados) => {
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
            },
            () => {
              // Las series fallidas se reintentan en el próximo polling.
            },
          )
        }
      } finally {
        seriesEnVueloRef.current = false
      }
    },
    [actualizarPuntos, ejecutarSeries],
  )

  const cargarHealth = useCallback(async () => {
    if (!activoRef.current || healthRef.current !== null) {
      return
    }

    await ejecutarHealth(
      (senal) => obtenerHealth(senal),
      (salud) => {
        healthRef.current = salud
        setHealth(salud)
      },
      () => {
        // Es opcional: solo controla la etiqueta de demo.
      },
    )
  }, [ejecutarHealth])

  const cargarAlertas = useCallback(
    () =>
      ejecutarAlertasSeguridad(
        (senal) => obtenerAlertasSeguridad(senal),
        (alertas) => {
          setAlertasSeguridad(alertas)
          setAlertasCargadas(true)
          setErrorAlertasSeguridad(null)
        },
        (mensaje) => {
          // Se conservan las alertas previas; el panel muestra el error.
          setErrorAlertasSeguridad(mensaje)
        },
      ),
    [ejecutarAlertasSeguridad],
  )

  const cargarAlertasActivas = useCallback(
    () =>
      ejecutarAlertasActivas(
        (senal) => obtenerAlertasActivas(senal),
        (alertas) => {
          setAlertasActivas(alertas)
          setErrorAlertas(null)
          setCargandoAlertas(false)
        },
        (mensaje) => {
          // Se conserva la lista previa; la sección muestra el error de lista.
          setErrorAlertas(mensaje)
          setCargandoAlertas(false)
        },
      ),
    [ejecutarAlertasActivas],
  )

  const invalidarCarrilAlertasActivas = useCallback(() => {
    alertasActivasControladorRef.current?.abort()
    alertasActivasSolicitudRef.current += 1
  }, [])

  const abortarCarriles = useCallback(() => {
    resumenControladorRef.current?.abort()
    resumenEventoControladorRef.current?.abort()
    seriesControladorRef.current?.abort()
    healthControladorRef.current?.abort()
    alertasControladorRef.current?.abort()
    alertasActivasControladorRef.current?.abort()
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

  const programarRefrescoAlertasActivas = useCallback(() => {
    if (timerAlertasActivasRef.current !== null) {
      window.clearTimeout(timerAlertasActivasRef.current)
    }
    timerAlertasActivasRef.current = window.setTimeout(() => {
      timerAlertasActivasRef.current = null
      void cargarAlertasActivas()
    }, RETRASO_ALERTAS_ACTIVAS_MS)
  }, [cargarAlertasActivas])

  const limpiarErrorAtender = useCallback(() => {
    setErrorAtender(null)
  }, [])

  const atenderAlerta = useCallback(
    async (id: number, nota?: string) => {
      if (atendiendoRef.current.has(id)) {
        return
      }
      atendiendoRef.current.add(id)
      setAtendiendo((actual) => ({ ...actual, [id]: true }))
      setErrorAtender(null)
      // Cualquier GET de la lista anterior queda invalidado antes del POST.
      invalidarCarrilAlertasActivas()

      try {
        const actualizada = await atenderAlertaApi(id, nota)
        if (!activoRef.current) {
          return
        }

        // Un GET que haya arrancado durante el POST tampoco puede pisar el
        // estado atendido que vamos a aplicar.
        invalidarCarrilAlertasActivas()
        setAlertasActivas((actual) => {
          if (actualizada.cerrada_en !== null) {
            return actual.filter((alerta) => alerta.id !== id)
          }
          return actual.map((alerta) =>
            alerta.id === id ? actualizada : alerta,
          )
        })
        // El resumen/KPIs se refrescan con el SSE `alerta_cerrada` (el backend
        // lo publica al atender) o con el polling si el stream está caído.
      } catch (fallo) {
        if (!activoRef.current) {
          return
        }

        if (fallo instanceof ErrorApi && fallo.status === 409) {
          // La alerta ya se cerró entre el render y el clic: refresca la lista.
          await cargarAlertasActivas()
          return
        }

        setErrorAtender(mensajeDeError(fallo))
      } finally {
        atendiendoRef.current.delete(id)
        if (activoRef.current) {
          setAtendiendo((actual) => {
            const siguiente = { ...actual }
            delete siguiente[id]
            return siguiente
          })
        }
      }
    },
    [cargarAlertasActivas, invalidarCarrilAlertasActivas],
  )

  useEffect(() => {
    activoRef.current = true
    // La carga arranca al montar; los setState ocurren después del primer
    // await, cuando ya hay respuesta de la API.
    void cargarResumen()
    void cargarHealth()
    void cargarAlertas()
    void cargarAlertasActivas()

    const intervalo = window.setInterval(() => {
      // Un solo tick de 60 s; cada carril conserva su propio abort/id.
      void cargarResumen()
      void cargarAlertas()
      void cargarAlertasActivas()
    }, INTERVALO_REFRESCO_MS)

    return () => {
      activoRef.current = false
      abortarCarriles()
      window.clearInterval(intervalo)
      if (timerResumenRef.current !== null) {
        window.clearTimeout(timerResumenRef.current)
        timerResumenRef.current = null
      }
      if (timerAlertasActivasRef.current !== null) {
        window.clearTimeout(timerAlertasActivasRef.current)
        timerAlertasActivasRef.current = null
      }
    }
  }, [
    cargarResumen,
    cargarHealth,
    cargarAlertas,
    cargarAlertasActivas,
    abortarCarriles,
  ])

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
    // Los eventos alerta_abierta/alerta_cerrada pudieron perderse durante la
    // caída; no esperamos al polling de 60 s para recuperar la lista.
    void cargarResumen()
    void cargarAlertas()
    void cargarAlertasActivas()
  }, [
    reconexiones,
    camaras,
    cargarSeries,
    cargarResumen,
    cargarAlertas,
    cargarAlertasActivas,
  ])

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

  const alRecibirAlertaOperativa = useCallback(() => {
    setUltimaActividadSse(new Date())
    programarRefrescoResumen()
    programarRefrescoAlertasActivas()
  }, [programarRefrescoResumen, programarRefrescoAlertasActivas])

  const alRecibirLoteActualizado = useCallback(() => {
    setUltimaActividadSse(new Date())
    programarRefrescoResumen()
  }, [programarRefrescoResumen])

  useStreamEvent('lectura', alRecibirLectura)
  useStreamEvent('kpis', alRecibirKpis)
  useStreamEvent('alerta_abierta', alRecibirAlertaOperativa)
  useStreamEvent('alerta_cerrada', alRecibirAlertaOperativa)
  useStreamEvent('lote_actualizado', alRecibirLoteActualizado)

  const refrescar = useCallback(async () => {
    if (!hayDatosRef.current) {
      setCargando(true)
    }
    await Promise.all([
      cargarResumen(),
      cargarHealth(),
      cargarAlertas(),
      cargarAlertasActivas(),
    ])
  }, [cargarResumen, cargarHealth, cargarAlertas, cargarAlertasActivas])

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
    errorAlertasSeguridad,
    alertasActivas,
    cargandoAlertas,
    errorAlertas,
    errorAtender,
    limpiarErrorAtender,
    atendiendo,
    atenderAlerta,
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
