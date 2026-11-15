/** Límites del contrato de auth, compartidos con el backend. */
export const LIMITES = {
  restauranteMin: 2,
  restauranteMax: 120,
  usuarioMin: 3,
  usuarioMax: 64,
  passwordMin: 8,
  passwordMax: 128,
} as const

/** Pydantic cuenta code points, no unidades UTF-16: los emojis valen 1. */
export function longitudTexto(texto: string): number {
  return [...texto].length
}

/** Devuelve el primer mensaje de validación del login, o `null` si está bien. */
export function validarLogin(usuario: string, password: string): string | null {
  if (!usuario || !password) {
    return 'Escribe tu usuario y contraseña.'
  }
  if (longitudTexto(usuario) > LIMITES.usuarioMax) {
    return `El usuario no puede superar los ${LIMITES.usuarioMax} caracteres.`
  }
  if (longitudTexto(password) > LIMITES.passwordMax) {
    return `La contraseña no puede superar los ${LIMITES.passwordMax} caracteres.`
  }
  return null
}

/** Devuelve el primer mensaje de validación del alta, o `null` si está bien. */
export function validarRegistro(
  restaurante: string,
  usuario: string,
  password: string,
  confirmacion: string,
): string | null {
  if (!restaurante) {
    return 'Escribe el nombre de tu restaurante.'
  }
  const largoRestaurante = longitudTexto(restaurante)
  if (
    largoRestaurante < LIMITES.restauranteMin ||
    largoRestaurante > LIMITES.restauranteMax
  ) {
    return `El restaurante debe tener entre ${LIMITES.restauranteMin} y ${LIMITES.restauranteMax} caracteres.`
  }

  if (!usuario) {
    return 'Escribe un usuario.'
  }
  const largoUsuario = longitudTexto(usuario)
  if (largoUsuario < LIMITES.usuarioMin || largoUsuario > LIMITES.usuarioMax) {
    return `El usuario debe tener entre ${LIMITES.usuarioMin} y ${LIMITES.usuarioMax} caracteres.`
  }

  const largoPassword = longitudTexto(password)
  if (
    largoPassword < LIMITES.passwordMin ||
    largoPassword > LIMITES.passwordMax
  ) {
    return `La contraseña debe tener entre ${LIMITES.passwordMin} y ${LIMITES.passwordMax} caracteres.`
  }

  if (password !== confirmacion) {
    return 'Las contraseñas no coinciden.'
  }
  return null
}
