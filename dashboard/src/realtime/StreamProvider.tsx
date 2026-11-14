import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  construirUrlStream,
  EVENTOS_STREAM,
  RECONEXION_MS,
  resolverApiUrl,
  type EventoStream,
} from './stream'

export { construirUrlStream, resolverApiUrl } from './stream'

export type OyenteStream = (evento: MessageEvent<string>) => void
type Suscriptores = Map<string, Set<OyenteStream>>

const StreamContext = createContext<Suscriptores | null>(null)

interface StreamProviderProps {
  children: ReactNode
  /**
   * JWT del usuario. La autenticación aún no existe: cuando haya login,
   * `main.tsx` (o el layout autenticado) pasa el token aquí.
   */
  token?: string
}

/**
 * Abre una sola conexión `EventSource` para todo el dashboard y reparte los
 * eventos por nombre entre los suscriptores de `useStreamEvent`.
 */
export function StreamProvider({ children, token }: StreamProviderProps) {
  const [suscriptores] = useState<Suscriptores>(() => new Map())

  useEffect(() => {
    const base = resolverApiUrl()
    if (!base || typeof EventSource === 'undefined') {
      return
    }

    const url = construirUrlStream(base, token)
    const estadoCerrado = EventSource.CLOSED
    let fuente: EventSource | null = null
    let alRecibir: ((evento: Event) => void) | null = null
    let timerReconexion: number | null = null
    let desmontado = false

    const desconectar = () => {
      if (!fuente) {
        return
      }
      if (alRecibir) {
        for (const nombre of EVENTOS_STREAM) {
          fuente.removeEventListener(nombre, alRecibir)
        }
      }
      fuente.close()
      fuente = null
      alRecibir = null
    }

    const programarReconexion = () => {
      if (desmontado || timerReconexion !== null) {
        return
      }
      timerReconexion = window.setTimeout(() => {
        timerReconexion = null
        conectar()
      }, RECONEXION_MS)
    }

    const conectar = () => {
      desconectar()

      const nueva = new EventSource(url)

      const despachar = (evento: Event) => {
        const mensaje = evento as MessageEvent<string>
        const oyentes = suscriptores.get(mensaje.type)
        if (!oyentes) {
          return
        }
        for (const oyente of oyentes) {
          oyente(mensaje)
        }
      }

      for (const nombre of EVENTOS_STREAM) {
        nueva.addEventListener(nombre, despachar)
      }

      nueva.onerror = () => {
        // CONNECTING: el navegador reintenta solo. CLOSED (502/503, 204 o
        // content-type inesperado): EventSource ya no vuelve, lo recreamos.
        if (nueva.readyState === estadoCerrado) {
          programarReconexion()
        }
      }

      fuente = nueva
      alRecibir = despachar
    }

    conectar()

    return () => {
      desmontado = true
      if (timerReconexion !== null) {
        window.clearTimeout(timerReconexion)
      }
      desconectar()
    }
  }, [suscriptores, token])

  return (
    <StreamContext.Provider value={suscriptores}>
      {children}
    </StreamContext.Provider>
  )
}

/**
 * Suscribe un oyente a un evento del stream compartido. Fuera de
 * `StreamProvider` no hace nada, así la vista se puede montar sin SSE.
 */
export function useStreamEvent(evento: EventoStream, oyente: OyenteStream) {
  const suscriptores = useContext(StreamContext)
  const oyenteRef = useRef(oyente)

  useEffect(() => {
    oyenteRef.current = oyente
  })

  useEffect(() => {
    if (!suscriptores) {
      return
    }

    const despachar = (mensaje: MessageEvent<string>) => {
      oyenteRef.current(mensaje)
    }

    const conjunto = suscriptores.get(evento) ?? new Set<OyenteStream>()
    conjunto.add(despachar)
    suscriptores.set(evento, conjunto)

    return () => {
      conjunto.delete(despachar)
      if (conjunto.size === 0) {
        suscriptores.delete(evento)
      }
    }
  }, [suscriptores, evento])
}
