import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { StreamProvider } from './realtime/StreamProvider.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <StreamProvider>
      <App />
    </StreamProvider>
  </StrictMode>,
)
