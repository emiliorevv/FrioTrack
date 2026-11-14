import { useEffect, useState } from 'react'

/**
 * Reloj de la vista. Un solo intervalo comparte el "ahora" entre los textos
 * "hace X" y "Actualizado hace X s" sin que cada tarjeta cree el suyo.
 */
export function useReloj(intervaloMs = 1000): Date {
  const [ahora, setAhora] = useState(() => new Date())

  useEffect(() => {
    const intervalo = window.setInterval(() => {
      setAhora(new Date())
    }, intervaloMs)

    return () => window.clearInterval(intervalo)
  }, [intervaloMs])

  return ahora
}
