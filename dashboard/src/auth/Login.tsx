import { useState, type FormEvent } from 'react'
import { useAuth } from './AuthProvider'
import { validarLogin, validarRegistro } from './validacion'

type Modo = 'login' | 'registro'

const TEXTOS_BOTON: Record<Modo, [string, string]> = {
  login: ['Entrar', 'Entrando…'],
  registro: ['Crear cuenta', 'Creando cuenta…'],
}

export function Login() {
  const { login, registro, cargando, error, limpiarError } = useAuth()
  const [modo, setModo] = useState<Modo>('login')
  const [restaurante, setRestaurante] = useState('')
  const [usuario, setUsuario] = useState('')
  const [password, setPassword] = useState('')
  const [confirmacion, setConfirmacion] = useState('')
  const [errorLocal, setErrorLocal] = useState<string | null>(null)

  const mensajeError = errorLocal ?? error
  const esDev = import.meta.env.DEV
  const mostrarDemo = esDev || import.meta.env.VITE_MOSTRAR_DEMO === '1'
  const [textoNormal, textoCargando] = TEXTOS_BOTON[modo]
  const textoBoton = cargando ? textoCargando : textoNormal

  function cambiarModo(nuevo: Modo) {
    if (nuevo === modo) {
      return
    }

    setModo(nuevo)
    setErrorLocal(null)
    // No se arrastra la contraseña de un formulario al otro.
    setPassword('')
    setConfirmacion('')
    limpiarError()
  }

  const alEnviar = async (evento: FormEvent<HTMLFormElement>) => {
    evento.preventDefault()
    if (cargando) {
      return
    }

    setErrorLocal(null)
    limpiarError()

    const usuarioLimpio = usuario.trim()

    if (modo === 'login') {
      const validacion = validarLogin(usuarioLimpio, password)
      if (validacion) {
        setErrorLocal(validacion)
        return
      }
      await login(usuarioLimpio, password)
      return
    }

    const restauranteLimpio = restaurante.trim()
    const validacion = validarRegistro(
      restauranteLimpio,
      usuarioLimpio,
      password,
      confirmacion,
    )
    if (validacion) {
      setErrorLocal(validacion)
      return
    }

    await registro(restauranteLimpio, usuarioLimpio, password)
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        <header>
          <p className="auth-brand">
            FríoTrack
            <span aria-hidden="true">.</span>
          </p>
          <p className="auth-subtitle">Monitoreo de cadena de frío</p>
        </header>

        <h1 className="auth-title">
          {modo === 'login' ? 'Iniciar sesión' : 'Crear cuenta'}
        </h1>

        {mensajeError && (
          <p className="auth-error" role="alert">
            {mensajeError}
          </p>
        )}

        <form
          key={modo}
          className="auth-form"
          onSubmit={alEnviar}
          noValidate
          aria-busy={cargando}
        >
          {modo === 'registro' && (
            <label className="auth-field">
              <span>Restaurante</span>
              <input
                type="text"
                name="restaurante"
                value={restaurante}
                onChange={(evento) => setRestaurante(evento.target.value)}
                autoComplete="organization"
                autoFocus
                required
                disabled={cargando}
              />
            </label>
          )}

          <label className="auth-field">
            <span>Usuario</span>
            <input
              type="text"
              name="usuario"
              value={usuario}
              onChange={(evento) => setUsuario(evento.target.value)}
              autoComplete="username"
              autoFocus={modo === 'login'}
              required
              disabled={cargando}
            />
          </label>

          <label className="auth-field">
            <span>Contraseña</span>
            <input
              type="password"
              name="password"
              value={password}
              onChange={(evento) => setPassword(evento.target.value)}
              autoComplete={
                modo === 'login' ? 'current-password' : 'new-password'
              }
              required
              disabled={cargando}
            />
          </label>

          {modo === 'registro' && (
            <label className="auth-field">
              <span>Confirmar contraseña</span>
              <input
                type="password"
                name="confirmacion"
                value={confirmacion}
                onChange={(evento) => setConfirmacion(evento.target.value)}
                autoComplete="new-password"
                required
                disabled={cargando}
              />
            </label>
          )}

          <button
            type="submit"
            className="auth-submit"
            disabled={cargando}
            aria-busy={cargando}
          >
            {textoBoton}
          </button>
        </form>

        <p className="auth-switch">
          {modo === 'login' ? '¿No tienes cuenta?' : '¿Ya tienes cuenta?'}{' '}
          <button
            type="button"
            className="auth-switch__link"
            onClick={() => cambiarModo(modo === 'login' ? 'registro' : 'login')}
            disabled={cargando}
          >
            {modo === 'login' ? 'Crear cuenta' : 'Ya tengo cuenta'}
          </button>
        </p>

        {mostrarDemo && (
          <p className="auth-demo">
            {esDev
              ? 'Demo: jefe / dueno / gerente · friotrack-demo'
              : 'Demo: usuarios jefe / dueno / gerente. Credenciales en el README.'}
          </p>
        )}
      </div>
    </main>
  )
}
