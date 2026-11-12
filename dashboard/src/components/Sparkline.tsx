import type { EstadoCamara } from '../types'
import { formatearRango, formatearTemperatura } from '../lib/format'

const ANCHO = 300
const ALTO = 52
const MARGEN_X = 2

interface SparklineProps {
  serie: number[]
  rangoMin: number
  rangoMax: number
  estado: EstadoCamara
  nombre: string
}

export function Sparkline({
  serie,
  rangoMin,
  rangoMax,
  estado,
  nombre,
}: SparklineProps) {
  if (serie.length < 2) {
    return null
  }

  const valores = [...serie, rangoMin, rangoMax]
  const minimo = Math.min(...valores)
  const maximo = Math.max(...valores)
  const margen = (maximo - minimo) * 0.18 || 1
  const dominioMin = minimo - margen
  const dominioMax = maximo + margen

  const y = (valor: number) =>
    ALTO - ((valor - dominioMin) / (dominioMax - dominioMin)) * ALTO

  const x = (indice: number) =>
    MARGEN_X + (indice / (serie.length - 1)) * (ANCHO - MARGEN_X * 2)

  const puntos = serie
    .map((valor, indice) => `${x(indice).toFixed(1)},${y(valor).toFixed(1)}`)
    .join(' ')

  const bandaY = Math.min(y(rangoMax), y(rangoMin))
  const bandaAlto = Math.abs(y(rangoMin) - y(rangoMax))

  const ultimo = serie[serie.length - 1]
  const ultimaX = x(serie.length - 1)
  const ultimaY = y(ultimo)

  return (
    <svg
      className={`sparkline sparkline--${estado}`}
      viewBox={`0 0 ${ANCHO} ${ALTO}`}
      role="img"
      aria-label={`Tendencia de ${nombre}: ${serie.length} lecturas, la última de ${formatearTemperatura(ultimo)} °C. Rango permitido de ${formatearRango(rangoMin)} a ${formatearRango(rangoMax)} °C.`}
    >
      <rect
        className="sparkline__band"
        x="0"
        y={bandaY}
        width={ANCHO}
        height={bandaAlto}
        rx="3"
      />
      <polyline className="sparkline__line" points={puntos} />
      <circle className="sparkline__dot" cx={ultimaX} cy={ultimaY} r="2.6" />
    </svg>
  )
}
