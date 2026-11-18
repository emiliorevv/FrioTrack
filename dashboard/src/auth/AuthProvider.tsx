import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  ErrorApi,
  iniciarSesion,
  registrar as registrarApi,
  type RespuestaLogin,
} from '../api/client'
import { decodificarJwt } from './jwt'
import { leerTokenGuardado, setToken, suscribirNoAutorizado } from './token'
import { LIMITES } from './validacion'

const MENSAJE_SESION_INVALIDA =
  'La sesión recibida no es válida. Intenta de nuevo.'
const MENSAJE_SESION_REGISTRO =
  'Tu cuenta se creó, pero no pudimos iniciar la sesión. Inicia sesión con tus credenciales.'

interface Sesion {
  token: string
  usuario: string
  rol: string
  restauranteId: number
  /** Segundos desde epoch, igual que el `exp` del JWT. */
  exp: number
}

interface BaseAuth {
  /** `true` mientras se procesa el login o el registro. */
  cargando: boolean
  error: string | null
  login: (usuario: string, password: string) => Promise<boolean>
  /** Crea restaurante y dueño; con éxito deja la sesión iniciada. */
  registro: (
    restaurante: string,
    usuario: string,
    password: string,
  ) => Promise<boolean>
  logout: () => void
  /** Limpia el error al cambiar de pestaña del formulario. */
  limpiarError: () => void
}

export interface Autenticado extends BaseAuth {
  token: string
  usuario: string
  rol: string
  restauranteId: number
  esDemo: boolean
}

export interface NoAutenticado extends BaseAuth {
  token: null
  usuario: null
  rol: null
  restauranteId: null
  esDemo: false
}

export type ContextoAuth = Autenticado | NoAutenticado

const AuthContext = createContext<ContextoAuth | null>(null)

function restaurarSesion(): Sesion | null {
  const token = leerTokenGuardado()
  if (!token) {
    return null
  }

  const payload = decodificarJwt(token)
  if (!payload || payload.exp * 1000 <= Date.now()) {
    setToken(null)
    return null
  }

  setToken(token)
  return {
    token,
    usuario: payload.usuario,
    rol: payload.rol,
    restauranteId: payload.restaurante_id,
    exp: payload.exp,
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [sesion, setSesion] = useState<Sesion | null>(restaurarSesion)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const timerExpiracionRef = useRef<number | null>(null)

  const limpiarExpiracion = useCallback(() => {
    if (timerExpiracionRef.current !== null) {
      window.clearTimeout(timerExpiracionRef.current)
      timerExpiracionRef.current = null
    }
  }, [])

  const aplicarSesion = useCallback((respuesta: RespuestaLogin): boolean => {
    const payload = decodificarJwt(respuesta.access_token)

    if (!payload || payload.exp * 1000 <= Date.now()) {
      return false
    }

    setToken(respuesta.access_token)
    setSesion({
      token: respuesta.access_token,
      usuario: payload.usuario,
      rol: payload.rol,
      restauranteId: payload.restaurante_id,
      exp: payload.exp,
    })
    return true
  }, [])

  const ejecutar = useCallback(
    async (
      peticion: () => Promise<RespuestaLogin>,
      mapearError: (fallo: unknown) => string,
      mensajeSesionInvalida = MENSAJE_SESION_INVALIDA,
    ): Promise<boolean> => {
      setCargando(true)
      setError(null)

      try {
        const respuesta = await peticion()
        if (aplicarSesion(respuesta)) {
          return true
        }

        setError(mensajeSesionInvalida)
        return false
      } catch (fallo) {
        setError(mapearError(fallo))
        return false
      } finally {
        setCargando(false)
      }
    },
    [aplicarSesion],
  )

  const login = useCallback(
    (usuario: string, password: string) =>
      ejecutar(() => iniciarSesion(usuario, password), mensajeDeLogin),
    [ejecutar],
  )

  const registro = useCallback(
    (restaurante: string, usuario: string, password: string) =>
      ejecutar(
        () => registrarApi(restaurante, usuario, password),
        mensajeDeRegistro,
        MENSAJE_SESION_REGISTRO,
      ),
    [ejecutar],
  )

  const limpiarError = useCallback(() => {
    setError(null)
  }, [])

  const logout = useCallback(() => {
    limpiarExpiracion()
    setToken(null)
    setSesion(null)
    setError(null)
  }, [limpiarExpiracion])

  useEffect(() => {
    limpiarExpiracion()
    if (!sesion) {
      return
    }

    const restante = sesion.exp * 1000 - Date.now()
    timerExpiracionRef.current = window.setTimeout(
      () => {
        timerExpiracionRef.current = null
        logout()
        setError('Tu sesión expiró. Inicia sesión de nuevo.')
      },
      Math.max(0, restante),
    )

    return limpiarExpiracion
  }, [sesion, logout, limpiarExpiracion])

  useEffect(() => {
    return suscribirNoAutorizado(() => {
      logout()
      setError('Tu sesión expiró. Inicia sesión de nuevo.')
    })
  }, [logout])

  const valor = useMemo<ContextoAuth>(() => {
    const base = { cargando, error, login, registro, logout, limpiarError }
    return sesion
      ? {
          ...base,
          token: sesion.token,
          usuario: sesion.usuario,
          rol: sesion.rol,
          restauranteId: sesion.restauranteId,
          esDemo: sesion.restauranteId === 1,
        }
      : {
          ...base,
          token: null,
          usuario: null,
          rol: null,
          restauranteId: null,
          esDemo: false,
        }
  }, [sesion, cargando, error, login, registro, logout, limpiarError])

  return <AuthContext.Provider value={valor}>{children}</AuthContext.Provider>
}

export function useAuth(): ContextoAuth {
  const contexto = useContext(AuthContext)
  if (!contexto) {
    throw new Error('useAuth debe usarse dentro de AuthProvider.')
  }
  return contexto
}

function sufijoReintento(segundos: number | null): string {
  return segundos !== null && segundos > 0
    ? ` Intenta de nuevo en ${segundos} s.`
    : ' Intenta de nuevo más tarde.'
}

function mensajeDeLogin(fallo: unknown): string {
  if (fallo instanceof ErrorApi) {
    if (fallo.status === 401) {
      return 'Usuario o contraseña incorrectos.'
    }
    if (fallo.status === 429) {
      return `Demasiados intentos de inicio de sesión.${sufijoReintento(fallo.retryAfterSegundos)}`
    }
    return fallo.detalle ?? 'No se pudo iniciar sesión.'
  }
  return 'No se pudo iniciar sesión. Revisa tu conexión.'
}

function mensajeDeRegistro(fallo: unknown): string {
  if (fallo instanceof ErrorApi) {
    if (fallo.status === 409) {
      return 'No se pudo completar el registro. Revisa los datos o prueba con otro usuario.'
    }
    if (fallo.status === 422) {
      return `Revisa los datos: restaurante ${LIMITES.restauranteMin}-${LIMITES.restauranteMax} caracteres, usuario ${LIMITES.usuarioMin}-${LIMITES.usuarioMax} y contraseña ${LIMITES.passwordMin}-${LIMITES.passwordMax}.`
    }
    if (fallo.status === 429) {
      return `Demasiados registros desde esta red.${sufijoReintento(fallo.retryAfterSegundos)}`
    }
    // Sin detalles técnicos del backend: el alta solo necesita una salida clara.
    return 'No se pudo crear la cuenta. Intenta de nuevo.'
  }
  return 'No se pudo crear la cuenta. Revisa tu conexión e intenta de nuevo.'
}
