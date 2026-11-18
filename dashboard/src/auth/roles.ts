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

/** Permiso de negocio: dueño y jefe de cocina administran el inventario. */
export function puedeEditarInventario(rol: string): boolean {
  return rol === 'dueno' || rol === 'jefe_cocina'
}

/** Permiso del panel de demo: solo el tenant demo y dueño/jefe de cocina. */
export function puedeSimularDemo(esDemo: boolean, rol: string): boolean {
  return esDemo && (rol === 'dueno' || rol === 'jefe_cocina')
}
