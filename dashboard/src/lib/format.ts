const formatoMxn = new Intl.NumberFormat('es-MX', {
  style: 'currency',
  currency: 'MXN',
  maximumFractionDigits: 0,
})

export function formatearMxn(valor: number): string {
  return formatoMxn.format(valor)
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
