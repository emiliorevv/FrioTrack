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
