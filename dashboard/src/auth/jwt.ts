import { esObjeto } from '../lib/validacion'

export interface PayloadJwt {
  usuario: string
  rol: string
  uid: number | null
  /** Tenant del usuario; 1 es el restaurante demo. */
  restaurante_id: number
  /** El backend lo agrega explícitamente para el tenant demo. */
  es_demo: boolean
  /** Segundos desde epoch. */
  exp: number
}

function decodificarBase64Url(texto: string): string {
  const base64 = texto.replace(/-/g, '+').replace(/_/g, '/')
  const relleno = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
  const binario = atob(relleno)
  const bytes = Uint8Array.from(binario, (caracter) => caracter.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

/**
 * Lee el payload del JWT para mostrar usuario/rol y caducidad. No verifica la
 * firma: eso es responsabilidad del backend en cada petición.
 */
export function decodificarJwt(token: string): PayloadJwt | null {
  const partes = token.split('.')
  if (partes.length !== 3) {
    return null
  }

  try {
    const datos: unknown = JSON.parse(decodificarBase64Url(partes[1]))
    if (!esObjeto(datos)) {
      return null
    }

    const {
      sub,
      rol,
      uid,
      exp,
      restaurante_id: restauranteId,
      es_demo: esDemoClaim,
    } = datos
    if (
      typeof sub !== 'string' ||
      typeof rol !== 'string' ||
      typeof exp !== 'number' ||
      typeof restauranteId !== 'number' ||
      !Number.isInteger(restauranteId) ||
      restauranteId <= 0 ||
      (esDemoClaim !== undefined && typeof esDemoClaim !== 'boolean')
    ) {
      return null
    }

    return {
      usuario: sub,
      rol,
      uid: typeof uid === 'number' ? uid : null,
      restaurante_id: restauranteId,
      // Compatibilidad temporal con el backend #66 (aún sin el claim).
      es_demo:
        typeof esDemoClaim === 'boolean' ? esDemoClaim : restauranteId === 1,
      exp,
    }
  } catch {
    return null
  }
}
