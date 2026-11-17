/** Guards genéricos compartidos por el cliente HTTP y los parsers de datos. */
export function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor)
}

/** Convierte un valor de input numérico; vacío/no finito devuelve `null`. */
export function aNumero(valor: string): number | null {
  const limpio = valor.trim()
  if (!limpio) {
    return null
  }
  const numero = Number(limpio)
  return Number.isFinite(numero) ? numero : null
}
