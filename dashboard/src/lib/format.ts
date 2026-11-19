import type { EstadoCamara, EstadoLote } from '../types'

/** Etiquetas de estado compartidas por tarjetas, filtros y configuración. */
export const ETIQUETA_ESTADO: Record<EstadoCamara, string> = {
  en_rango: 'En rango',
  alerta: 'Alerta',
  critica: 'Crítica',
}

const formatoMxn = new Intl.NumberFormat('es-MX', {
  style: 'currency',
  currency: 'MXN',
  maximumFractionDigits: 0,
})

const formatoMxnCentavos = new Intl.NumberFormat('es-MX', {
  style: 'currency',
  currency: 'MXN',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const formatoCantidad = new Intl.NumberFormat('es-MX', {
  maximumFractionDigits: 2,
})

const formatoEscala = new Intl.NumberFormat('es-MX', {
  maximumFractionDigits: 1,
})

const formatoFecha = new Intl.DateTimeFormat('es-MX', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})

export function formatearMxn(valor: number): string {
  return formatoMxn.format(valor)
}

/** Para costos de inventario: conserva centavos. */
export function formatearMxnConCentavos(valor: number): string {
  return formatoMxnCentavos.format(valor)
}

export function formatearCantidadLote(valor: number): string {
  return formatoCantidad.format(valor)
}

/** Etiquetas de estado de un lote. */
export const ETIQUETA_ESTADO_LOTE: Record<EstadoLote, string> = {
  ok: 'Ok',
  en_riesgo: 'En riesgo',
  merma: 'Merma',
}

/** Fecha ISO `YYYY-MM-DD` a texto local, sin desplazar el día por zona horaria. */
export function formatearFecha(iso: string): string {
  const fecha = new Date(`${iso}T12:00:00`)
  return Number.isNaN(fecha.getTime()) ? iso : formatoFecha.format(fecha)
}

/** `true` si la fecha de caducidad ya pasó (el día de hoy todavía es válido). */
export function fechaVencida(iso: string, ahora = new Date()): boolean {
  const partes = iso.split('-').map(Number)
  if (partes.length !== 3 || partes.some((parte) => !Number.isFinite(parte))) {
    return false
  }
  const [anio, mes, dia] = partes
  const fecha = new Date(anio, mes - 1, dia)
  const hoy = new Date(ahora.getFullYear(), ahora.getMonth(), ahora.getDate())
  return fecha.getTime() < hoy.getTime()
}

/** Un solo decimal y signo menos tipográfico (−), no guion. */
export function formatearTemperatura(valor: number): string {
  return valor.toFixed(1).replace('-', '−')
}

/** Para rangos: 0–2 se lee mejor que 0.0–2.0; conserva medios grados. */
export function formatearRango(valor: number): string {
  const texto = Number.isInteger(valor) ? String(valor) : valor.toFixed(1)
  return texto.replace('-', '−')
}

export function formatearHace(ts: string, ahora: Date): string {
  const segundos = Math.max(
    0,
    Math.round((ahora.getTime() - new Date(ts).getTime()) / 1000),
  )

  if (segundos < 60) {
    return `hace ${segundos} s`
  }

  return `hace ${Math.round(segundos / 60)} min`
}

interface TiempoRegla {
  valor: number
  unidad: 's' | 'ms'
}

function medirTiempoRegla(segundos: number): TiempoRegla {
  if (segundos < 1) {
    return {
      valor: Math.max(1, Math.round(segundos * 1000)),
      unidad: 'ms',
    }
  }
  return { valor: segundos, unidad: 's' }
}

/** "2 s", "2.5 s", "17 ms"; nunca "0 s" para escalas muy grandes. */
export function formatearSegundosRegla(segundos: number): string {
  if (!Number.isFinite(segundos) || segundos <= 0) {
    return '—'
  }
  const { valor, unidad } = medirTiempoRegla(segundos)
  return `${formatoEscala.format(valor)} ${unidad}`
}

/** "2 segundos", "1 segundo", "17 milisegundos" para el tooltip. */
export function formatearSegundosReglaLarga(segundos: number): string {
  if (!Number.isFinite(segundos) || segundos <= 0) {
    return '—'
  }
  const { valor, unidad } = medirTiempoRegla(segundos)
  const etiqueta =
    unidad === 's'
      ? valor === 1
        ? 'segundo'
        : 'segundos'
      : valor === 1
        ? 'milisegundo'
        : 'milisegundos'
  return `${formatoEscala.format(valor)} ${etiqueta}`
}

/** Singular/plural por número real, no por el texto ya formateado. */
export function esTiempoReglaSingular(segundos: number): boolean {
  if (!Number.isFinite(segundos) || segundos <= 0) {
    return false
  }
  return medirTiempoRegla(segundos).valor === 1
}
