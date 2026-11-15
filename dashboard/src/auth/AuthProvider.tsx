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

interface Sesion {
  token: string
  usuario: string
  rol: string
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
}

export interface NoAutenticado extends BaseAuth {
  token: null
  usuario: null
  rol: null
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
      setError('La sesión recibida no es válida. Intenta de nuevo.')
      return false
    }

    setToken(respuesta.access_token)
    setSesion({
      token: respuesta.access_token,
      usuario: payload.usuario,
      rol: payload.rol,
      exp: payload.exp,
    })
    return true
  }, [])

  const login = useCallback(
    async (usuario: string, password: string) => {
      setCargando(true)
      setError(null)

      try {
        const respuesta = await iniciarSesion(usuario, password)
        return aplicarSesion(respuesta)
      } catch (fallo) {
        setError(mensajeDeLogin(fallo))
        return false
      } finally {
        setCargando(false)
      }
    },
    [aplicarSesion],
  )

  const registro = useCallback(
    async (restaurante: string, usuario: string, password: string) => {
      setCargando(true)
      setError(null)

      try {
        const respuesta = await registrarApi(restaurante, usuario, password)
        return aplicarSesion(respuesta)
      } catch (fallo) {
        setError(mensajeDeRegistro(fallo))
        return false
      } finally {
        setCargando(false)
      }
    },
    [aplicarSesion],
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
        }
      : { ...base, token: null, usuario: null, rol: null }
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

function mensajeDeLogin(fallo: unknown): string {
  if (fallo instanceof ErrorApi) {
    if (fallo.status === 401) {
      return 'Usuario o contraseña incorrectos.'
    }
    if (fallo.status === 429) {
      const base = 'Demasiados intentos de inicio de sesión.'
      return fallo.retryAfterSegundos !== null
        ? `${base} Intenta de nuevo en ${fallo.retryAfterSegundos} s.`
        : base
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
      return 'Revisa los datos: usuario mínimo 3 caracteres y contraseña mínimo 8.'
    }
    if (fallo.status === 429) {
      const base = 'Demasiados registros desde esta red.'
      return fallo.retryAfterSegundos !== null
        ? `${base} Intenta de nuevo en ${fallo.retryAfterSegundos} s.`
        : `${base} Intenta de nuevo más tarde.`
    }
    // Sin detalles técnicos del backend: el alta solo necesita una salida clara.
    return 'No se pudo crear la cuenta. Intenta de nuevo.'
  }
  return 'No se pudo crear la cuenta. Revisa tu conexión e intenta de nuevo.'
}
