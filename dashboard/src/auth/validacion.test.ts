import { describe, expect, it } from 'vitest'
import {
  LIMITES,
  longitudTexto,
  validarLogin,
  validarRegistro,
} from './validacion'

describe('longitudTexto', () => {
  it('cuenta code points y no unidades UTF-16', () => {
    expect(longitudTexto('😀😀😀😀')).toBe(4)
    expect('😀😀😀😀'.length).toBe(8)
  })
})

describe('validarLogin', () => {
  it('acepta credenciales dentro de los límites', () => {
    expect(validarLogin('jefe', 'friotrack-demo')).toBeNull()
  })

  it('exige usuario y contraseña', () => {
    expect(validarLogin('', 'friotrack-demo')).toBe(
      'Escribe tu usuario y contraseña.',
    )
    expect(validarLogin('jefe', '')).toBe('Escribe tu usuario y contraseña.')
  })

  it('rechaza usuario de 65 caracteres y contraseña de 129', () => {
    expect(validarLogin('u'.repeat(LIMITES.usuarioMax + 1), 'clave')).toBe(
      `El usuario no puede superar los ${LIMITES.usuarioMax} caracteres.`,
    )
    expect(validarLogin('jefe', 'p'.repeat(LIMITES.passwordMax + 1))).toBe(
      `La contraseña no puede superar los ${LIMITES.passwordMax} caracteres.`,
    )
  })
})

describe('validarRegistro', () => {
  const valido = {
    restaurante: 'Taquería del Norte',
    usuario: 'dueno-nuevo',
    password: 'friotrack-demo',
    confirmacion: 'friotrack-demo',
  }

  it('acepta un alta válida', () => {
    expect(
      validarRegistro(
        valido.restaurante,
        valido.usuario,
        valido.password,
        valido.confirmacion,
      ),
    ).toBeNull()
  })

  it('exige restaurante y usuario', () => {
    expect(
      validarRegistro('', valido.usuario, valido.password, valido.confirmacion),
    ).toBe('Escribe el nombre de tu restaurante.')
    expect(
      validarRegistro(
        valido.restaurante,
        '',
        valido.password,
        valido.confirmacion,
      ),
    ).toBe('Escribe un usuario.')
  })

  it('rechaza restaurante de 1 carácter y de 121', () => {
    const mensaje = 'El restaurante debe tener entre 2 y 120 caracteres.'
    expect(
      validarRegistro(
        'A',
        valido.usuario,
        valido.password,
        valido.confirmacion,
      ),
    ).toBe(mensaje)
    expect(
      validarRegistro(
        'R'.repeat(LIMITES.restauranteMax + 1),
        valido.usuario,
        valido.password,
        valido.confirmacion,
      ),
    ).toBe(mensaje)
  })

  it('rechaza usuario de 2 y de 65 caracteres', () => {
    const mensaje = 'El usuario debe tener entre 3 y 64 caracteres.'
    expect(
      validarRegistro(
        valido.restaurante,
        'ab',
        valido.password,
        valido.confirmacion,
      ),
    ).toBe(mensaje)
    expect(
      validarRegistro(
        valido.restaurante,
        'u'.repeat(LIMITES.usuarioMax + 1),
        valido.password,
        valido.confirmacion,
      ),
    ).toBe(mensaje)
  })

  it('cuenta emojis como code points en la contraseña', () => {
    expect(
      validarRegistro(
        valido.restaurante,
        valido.usuario,
        '😀😀😀😀',
        '😀😀😀😀',
      ),
    ).toBe('La contraseña debe tener entre 8 y 128 caracteres.')
  })

  it('rechaza contraseña de 129 caracteres', () => {
    expect(
      validarRegistro(
        valido.restaurante,
        valido.usuario,
        'p'.repeat(LIMITES.passwordMax + 1),
        'p'.repeat(LIMITES.passwordMax + 1),
      ),
    ).toBe('La contraseña debe tener entre 8 y 128 caracteres.')
  })

  it('exige que la confirmación coincida', () => {
    expect(
      validarRegistro(
        valido.restaurante,
        valido.usuario,
        valido.password,
        'otra-clave',
      ),
    ).toBe('Las contraseñas no coinciden.')
  })
})
