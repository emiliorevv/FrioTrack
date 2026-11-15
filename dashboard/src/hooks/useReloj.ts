import { useSyncExternalStore } from 'react'

/**
 * Reloj compartido del dashboard.
 *
 * El store vive a nivel de módulo: todos los textos "hace X" leen el mismo
 * `ahora` y hay un solo `setInterval` mientras quede algún suscriptor.
 */
const INTERVALO_MS = 1000

let ahora = new Date()
let temporizador: number | null = null
const oyentes = new Set<() => void>()

function notificar() {
  ahora = new Date()
  for (const oyente of oyentes) {
    oyente()
  }
}

function suscribir(oyente: () => void) {
  oyentes.add(oyente)

  if (temporizador === null) {
    // Al arrancar el primer consumidor, alinea el snapshot con el reloj real.
    ahora = new Date()
    temporizador = window.setInterval(notificar, INTERVALO_MS)
  }

  return () => {
    oyentes.delete(oyente)
    if (oyentes.size === 0 && temporizador !== null) {
      window.clearInterval(temporizador)
      temporizador = null
    }
  }
}

function obtenerAhora(): Date {
  return ahora
}

/** Devuelve el `ahora` compartido; no crea intervalos por componente. */
export function useReloj(): Date {
  return useSyncExternalStore(suscribir, obtenerAhora, obtenerAhora)
}
