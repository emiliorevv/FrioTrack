/**
 * Utilidades compartidas por los eventos SSE.
 *
 * Los `data:` del stream son siempre JSON con un objeto arriba. Un payload
 * inválido no debe romper el dashboard: `parsearJson` devuelve `null`.
 */
export function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor)
}

export function parsearJson(texto: string): unknown | null {
  try {
    return JSON.parse(texto)
  } catch {
    return null
  }
}
