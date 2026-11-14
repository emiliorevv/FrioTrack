import { useCallback, useEffect, useRef, useState } from 'react'
import {
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
} from '../api/client'
import { useStreamEvent } from '../realtime/StreamProvider'
import type {
  Camara,
  EstadoCamara,
  Health,
  Kpis,
  LecturaStream,
  SerieCamara,
} from '../types'

/** Respaldo por si el SSE se cae: vuelve a preguntar toda la base. */
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
 */
export function useDashboard(): EstadoDashboard {
  const [health, setHealth] = useState<Health | null>(null)
  const [camaras, setCamaras] = useState<Camara[]>([])
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [series, setSeries] = useState<Record<number, SerieCamara>>({})
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actualizadoEn, setActualizadoEn] = useState<Date | null>(null)

  const activoRef = useRef(false)
  const hayDatosRef = useRef(false)
  const timerResumenRef = useRef<number | null>(null)

  const refrescar = useCallback(async () => {
    const primera = !hayDatosRef.current

    try {
      const [salud, lista, kpisNuevos] = await Promise.all([
        obtenerHealth(),
        obtenerCamaras(),
        obtenerKpis(),
      ])
      if (!activoRef.current) {
        return
      }

      setHealth(salud)
      setCamaras(lista)
      setKpis(kpisNuevos)
      setActualizadoEn(new Date())
      setError(null)
      hayDatosRef.current = true
      if (primera) {
        setCargando(false)
      }

      const seriesNuevas = await cargarSeries(lista)
      if (activoRef.current) {
        setSeries(seriesNuevas)
      }
    } catch (fallo) {
      if (activoRef.current) {
        setError(mensajeDeError(fallo))
      }
    } finally {
      if (activoRef.current && primera) {
        setCargando(false)
      }
    }
  }, [])

  const refrescarResumen = useCallback(async () => {
    try {
      const [lista, kpisNuevos] = await Promise.all([
        obtenerCamaras(),
        obtenerKpis(),
      ])
      if (!activoRef.current) {
        return
      }

      setCamaras(lista)
      setKpis(kpisNuevos)
      setActualizadoEn(new Date())
      setError(null)
    } catch {
      // Se conserva lo que ya está en pantalla; el polling de respaldo reintenta.
    }
  }, [])

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
    // La carga debe arrancar al montar; los setState de `refrescar` ocurren
    // después del primer await, cuando ya hay respuesta de la API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refrescar()
    const intervalo = window.setInterval(() => {
      void refrescar()
    }, INTERVALO_REFRESCO_MS)

    return () => {
      activoRef.current = false
      window.clearInterval(intervalo)
      if (timerResumenRef.current !== null) {
        window.clearTimeout(timerResumenRef.current)
        timerResumenRef.current = null
      }
    }
  }, [refrescar])

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

  return {
    health,
    camaras,
    kpis,
    series,
    cargando,
    error,
    actualizadoEn,
    refrescar,
  }
}

/** Una serie fallida no tumba la carga: esa cámara queda sin sparkline. */
async function cargarSeries(
  camaras: Camara[],
): Promise<Record<number, SerieCamara>> {
  const resultados = await Promise.allSettled(
    camaras.map((camara) => obtenerLecturas(camara.id)),
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

function mensajeDeError(fallo: unknown): string {
  if (fallo instanceof Error && fallo.message) {
    return fallo.message
  }
  return 'No se pudo conectar con la API de FríoTrack.'
}

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null
}

function leerJson(texto: string): unknown {
  try {
    return JSON.parse(texto)
  } catch {
    return null
  }
}

function esEstado(valor: unknown): valor is EstadoCamara {
  return valor === 'en_rango' || valor === 'alerta' || valor === 'critica'
}

function leerLectura(texto: string): LecturaStream | null {
  const datos = leerJson(texto)
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
  const datos = leerJson(texto)
  return esKpis(datos) ? datos : null
}
