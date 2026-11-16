import { describe, expect, it } from 'vitest'
import { ErrorApi } from '../api/client'
import { mensajeDeError } from './erroresApi'

describe('mensajeDeError', () => {
  it('explica un 401 sin romper la vista', () => {
    expect(mensajeDeError(new ErrorApi('No autorizado', 401))).toMatch(
      /sesión expiró/i,
    )
  })

  it('explica un 403 de rol', () => {
    expect(mensajeDeError(new ErrorApi('Prohibido', 403))).toMatch(
      /Solo el dueño/i,
    )
  })

  it('conserva el detail de un 404', () => {
    expect(
      mensajeDeError(
        new ErrorApi('Sensor no encontrado', 404, null, 'Sensor no encontrado'),
      ),
    ).toBe('Sensor no encontrado')
  })

  it('da un mensaje propio a un 404 sin detail', () => {
    expect(mensajeDeError(new ErrorApi('La API respondió 404', 404))).toMatch(
      /ya no existe/i,
    )
  })

  it('muestra el detail de un 409 de datos asociados', () => {
    const detalle =
      'La cámara tiene datos asociados; desactívala o elimina primero sus sensores.'
    expect(mensajeDeError(new ErrorApi(detalle, 409, null, detalle))).toBe(
      detalle,
    )
  })

  it('usa el resumen de cámara en un 422 sin detalle', () => {
    expect(
      mensajeDeError(
        new ErrorApi('La API respondió 422 Unprocessable Entity', 422),
        'camara',
      ),
    ).toBe('Revisa el nombre, el rango y los minutos.')
  })

  it('usa el resumen de sensor en un 422 sin detalle', () => {
    expect(
      mensajeDeError(
        new ErrorApi('La API respondió 422 Unprocessable Entity', 422),
        'sensor',
      ),
    ).toBe('Revisa los datos del sensor.')
  })

  it('prioriza el detalle real de FastAPI en un 422', () => {
    expect(
      mensajeDeError(
        new ErrorApi(
          'activo debe ser booleano',
          422,
          null,
          'activo debe ser booleano',
        ),
        'sensor',
      ),
    ).toBe('activo debe ser booleano')
  })

  it('usa el mensaje de errores desconocidos', () => {
    expect(mensajeDeError(new Error('sin red'))).toBe('sin red')
    expect(mensajeDeError('texto')).toMatch(/inesperado/i)
  })
})
