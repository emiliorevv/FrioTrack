import { useReloj } from '../hooks/useReloj'
import { formatearHace } from '../lib/format'

interface TiempoRelativoProps {
  /** Momento del evento, ISO 8601. */
  ts: string
  className?: string
}

/**
 * Texto "hace X" con su propio reloj: solo este nodo se re-renderiza cada
 * segundo, no la tarjeta ni el panel que lo contienen.
 */
export function TiempoRelativo({ ts, className }: TiempoRelativoProps) {
  const ahora = useReloj()

  return (
    <time className={className} dateTime={ts}>
      {formatearHace(ts, ahora)}
    </time>
  )
}
