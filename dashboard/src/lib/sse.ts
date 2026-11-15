/**
 * Parser de los `data:` del stream SSE.
 *
 * Un payload inválido no debe romper el dashboard: `parsearJson` devuelve
 * `null`. La validación de forma vive en cada hook o en `lib/validacion`.
 */
export function parsearJson(texto: string): unknown | null {
  try {
    return JSON.parse(texto)
  } catch {
    return null
  }
}
