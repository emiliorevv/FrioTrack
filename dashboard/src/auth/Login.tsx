import { useState, type FormEvent } from 'react'
import { useAuth } from './AuthProvider'

type Modo = 'login' | 'registro'

/** Devuelve el primer mensaje de validación del alta, o `null` si está bien. */
function validarRegistro(
  restaurante: string,
  usuario: string,
  password: string,
  confirmacion: string,
): string | null {
  if (!restaurante) {
    return 'Escribe el nombre de tu restaurante.'
  }
  if (!usuario) {
    return 'Escribe un usuario.'
  }
  if (usuario.length < 3) {
    return 'El usuario debe tener al menos 3 caracteres.'
  }
  if (password.length < 8) {
    return 'La contraseña debe tener al menos 8 caracteres.'
  }
  if (password !== confirmacion) {
    return 'Las contraseñas no coinciden.'
  }
  return null
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
  const textoBoton =
    modo === 'login'
      ? cargando
        ? 'Entrando…'
        : 'Entrar'
      : cargando
        ? 'Creando cuenta…'
        : 'Crear cuenta'

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
      if (!usuarioLimpio || !password) {
        setErrorLocal('Escribe tu usuario y contraseña.')
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

        {import.meta.env.DEV && (
          <p className="auth-demo">Demo: jefe / friotrack-demo</p>
        )}
      </div>
    </main>
  )
}
