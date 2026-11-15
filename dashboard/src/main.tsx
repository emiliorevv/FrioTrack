import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AuthProvider, useAuth } from './auth/AuthProvider.tsx'
import { Login } from './auth/Login.tsx'
import { StreamProvider } from './realtime/StreamProvider.tsx'

function Raiz() {
  const { token } = useAuth()

  if (!token) {
    return <Login />
  }

  return (
    <StreamProvider token={token}>
      <App />
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
