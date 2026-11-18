import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AuthProvider, useAuth } from './auth/AuthProvider.tsx'
import { Login } from './auth/Login.tsx'
import { StreamProvider } from './realtime/StreamProvider.tsx'

function Raiz() {
  const auth = useAuth()

  if (auth.token === null) {
    return <Login />
  }

  return (
    <StreamProvider token={auth.token}>
      <App
        usuario={auth.usuario}
        rol={auth.rol}
        esDemo={auth.esDemo}
        onLogout={auth.logout}
      />
    </StreamProvider>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <Raiz />
    </AuthProvider>
  </StrictMode>,
)
