import { useState, type FormEvent } from 'react'
import { useAuth } from './AuthProvider'

export function Login() {
  const { login, cargando, error } = useAuth()
  const [usuario, setUsuario] = useState('')
  const [password, setPassword] = useState('')

  const alEnviar = async (evento: FormEvent<HTMLFormElement>) => {
    evento.preventDefault()
    await login(usuario.trim(), password)
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

        <h1 className="auth-title">Iniciar sesión</h1>

        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}

        <form className="auth-form" onSubmit={alEnviar}>
          <label className="auth-field">
            <span>Usuario</span>
            <input
              type="text"
              name="usuario"
              value={usuario}
              onChange={(evento) => setUsuario(evento.target.value)}
              autoComplete="username"
              autoFocus
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
              autoComplete="current-password"
              required
              disabled={cargando}
            />
          </label>

          <button
            type="submit"
            className="auth-submit"
            disabled={cargando}
            aria-busy={cargando}
          >
            {cargando ? 'Entrando…' : 'Entrar'}
          </button>
        </form>

        {import.meta.env.DEV && (
          <p className="auth-demo">Demo: jefe / friotrack-demo</p>
        )}
      </div>
    </main>
  )
}
