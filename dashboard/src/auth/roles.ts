/** Etiqueta legible para el rol del JWT. */
export function etiquetaRol(rol: string): string {
  if (rol === 'jefe_cocina') {
    return 'Jefe de cocina'
  }
  if (rol === 'gerente') {
    return 'Gerente'
  }
  return rol || 'Usuario'
}
