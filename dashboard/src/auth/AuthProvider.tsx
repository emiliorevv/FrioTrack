import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { ErrorApi, iniciarSesion } from '../api/client'
import { decodificarJwt } from './jwt'
import { leerTokenGuardado, setToken, suscribirNoAutorizado } from './token'

interface Sesion {
  token: string
  usuario: string
  rol: string
}

export interface ContextoAuth {
  token: string | null
  usuario: string | null
  rol: string | null
  /** `true` mientras se procesa el login. */
  cargando: boolean
  error: string | null
  login: (usuario: string, password: string) => Promise<boolean>
  logout: () => void
}

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
  return { token, usuario: payload.usuario, rol: payload.rol }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [sesion, setSesion] = useState<Sesion | null>(restaurarSesion)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const login = useCallback(async (usuario: string, password: string) => {
    setCargando(true)
    setError(null)

    try {
      const respuesta = await iniciarSesion(usuario, password)
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
      })
      return true
    } catch (fallo) {
      setError(mensajeDeLogin(fallo))
      return false
    } finally {
      setCargando(false)
    }
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setSesion(null)
    setError(null)
  }, [])

  useEffect(() => {
    return suscribirNoAutorizado(() => {
      setToken(null)
      setSesion(null)
      setError('Tu sesión expiró. Inicia sesión de nuevo.')
    })
  }, [])

  const valor = useMemo<ContextoAuth>(
    () => ({
      token: sesion?.token ?? null,
      usuario: sesion?.usuario ?? null,
      rol: sesion?.rol ?? null,
      cargando,
      error,
      login,
      logout,
    }),
    [sesion, cargando, error, login, logout],
  )

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
      return 'Usuario o contraseña incorrectos'
    }
    if (fallo.status === 429) {
      const base = fallo.message || 'Demasiados intentos de inicio de sesión.'
      return fallo.retryAfterSegundos !== null
        ? `${base} Intenta de nuevo en ${fallo.retryAfterSegundos} s.`
        : base
    }
    return fallo.message || 'No se pudo iniciar sesión.'
  }
  return 'No se pudo iniciar sesión. Revisa tu conexión.'
}
