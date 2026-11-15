import { describe, expect, it } from 'vitest'
import { etiquetaRol, puedeAtenderAlertas } from './roles'

describe('puedeAtenderAlertas', () => {
  it('habilita al dueño y al jefe de cocina', () => {
    expect(puedeAtenderAlertas('dueno')).toBe(true)
    expect(puedeAtenderAlertas('jefe_cocina')).toBe(true)
    expect(puedeAtenderAlertas('gerente')).toBe(false)
    expect(puedeAtenderAlertas('admin')).toBe(false)
  })
})

describe('etiquetaRol', () => {
  it('etiqueta los roles conocidos y conserva los desconocidos', () => {
    expect(etiquetaRol('dueno')).toBe('Dueño')
    expect(etiquetaRol('jefe_cocina')).toBe('Jefe de cocina')
    expect(etiquetaRol('gerente')).toBe('Gerente')
    expect(etiquetaRol('admin')).toBe('admin')
    expect(etiquetaRol('')).toBe('Usuario')
  })
})
