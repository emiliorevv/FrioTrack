/** Etiqueta legible para el rol del JWT. */
export function etiquetaRol(rol: string): string {
  if (rol === 'dueno') {
    return 'Dueño'
  }
  if (rol === 'jefe_cocina') {
    return 'Jefe de cocina'
  }
  if (rol === 'gerente') {
    return 'Gerente'
  }
  return rol || 'Usuario'
}

/** Permiso de negocio: el dueño y el jefe de cocina atienden alertas. */
export function puedeAtenderAlertas(rol: string): boolean {
  return rol === 'dueno' || rol === 'jefe_cocina'
}
