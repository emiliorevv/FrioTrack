/**
 * Resuelve la base de la API.
 *
 * - Con `VITE_API_URL`: quita espacios y slashes finales.
 * - Sin valor en desarrollo: cae al backend local.
 * - Sin valor en producción: no adivina un host (nada de mixed content) y
 *   devuelve `null` para no hacer peticiones.
 */
export function resolverApiUrl(
  configurada = import.meta.env.VITE_API_URL,
  esDev = import.meta.env.DEV,
): string | null {
  const base = configurada?.trim().replace(/\/+$/, '')

  if (base) {
    return base
  }

  if (esDev) {
    return 'http://127.0.0.1:8000/api'
  }

  console.error(
    'Falta VITE_API_URL: el dashboard no puede hablar con la API en producción.',
  )
  return null
}
