const CLAVE_TOKEN = 'friotrack.token'

type OyenteNoAutorizado = () => void

const oyentes = new Set<OyenteNoAutorizado>()

function leerDeSesion(): string | null {
  try {
    return sessionStorage.getItem(CLAVE_TOKEN)
  } catch {
    return null
  }
}

let tokenActual: string | null = null

/** Token vigente en memoria, listo para el cliente HTTP. */
export function getToken(): string | null {
  return tokenActual
}

/** Token persistido en esta pestaña; el provider lo usa al restaurar. */
export function leerTokenGuardado(): string | null {
  return leerDeSesion()
}

export function setToken(token: string | null): void {
  tokenActual = token

  try {
    if (token) {
      sessionStorage.setItem(CLAVE_TOKEN, token)
    } else {
      sessionStorage.removeItem(CLAVE_TOKEN)
    }
  } catch {
    // sessionStorage puede no estar disponible (modo privado).
  }
}

/** Avisa a la capa de auth cuando una llamada autenticada recibe 401. */
export function suscribirNoAutorizado(oyente: OyenteNoAutorizado): () => void {
  oyentes.add(oyente)
  return () => {
    oyentes.delete(oyente)
  }
}

export function notificarNoAutorizado(): void {
  for (const oyente of [...oyentes]) {
    oyente()
  }
}
