/** Guards genéricos compartidos por el cliente HTTP y los parsers de datos. */
export function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor)
}
