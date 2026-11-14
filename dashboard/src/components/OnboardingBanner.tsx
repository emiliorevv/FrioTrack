import { useState } from 'react'

const CLAVE_CERRADO = 'friotrack:onboarding-cerrado'

function bannerYaCerrado(): boolean {
  try {
    return window.localStorage.getItem(CLAVE_CERRADO) === '1'
  } catch {
    return false
  }
}

export function OnboardingBanner() {
  const [visible, setVisible] = useState(() => !bannerYaCerrado())

  if (!visible) {
    return null
  }

  function cerrar() {
    setVisible(false)
    try {
      window.localStorage.setItem(CLAVE_CERRADO, '1')
    } catch {
      /* La demo funciona igual sin recordar el cierre. */
    }
  }

  return (
    <aside className="onboarding" aria-label="Aviso de bienvenida">
      <span className="onboarding__icon" aria-hidden="true">
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.5 8.6 8.6 0 0 1-3.9-.9L3 21l1.9-5.3A8.4 8.4 0 1 1 21 11.5Z" />
        </svg>
      </span>

      <p className="onboarding__text">
        FríoTrack vigila tus cámaras. Si algo sale de rango, te avisa en el
        dashboard.
      </p>

      <button
        type="button"
        className="icon-button"
        onClick={cerrar}
        aria-label="Cerrar aviso"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <path d="m6 6 12 12M18 6 6 18" />
        </svg>
      </button>
    </aside>
  )
}
