import { afterEach, describe, expect, it, vi } from 'vitest'
import { construirUrlStream, resolverApiUrl } from './stream'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('resolverApiUrl', () => {
  it('recorta espacios y slashes finales del valor configurado', () => {
    expect(resolverApiUrl(' https://api.prueba.mx/api/// ', true)).toBe(
      'https://api.prueba.mx/api',
    )
  })

  it('cae al backend local en desarrollo si no hay valor', () => {
    expect(resolverApiUrl('', true)).toBe('http://127.0.0.1:8000/api')
    expect(resolverApiUrl('   ', true)).toBe('http://127.0.0.1:8000/api')
  })

  it('devuelve null en producción sin VITE_API_URL y avisa en consola', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(resolverApiUrl('', false)).toBeNull()
    expect(error).toHaveBeenCalledTimes(1)
  })
})

describe('construirUrlStream', () => {
  it('añade /stream sin token cuando no hay JWT', () => {
    expect(construirUrlStream('https://api.prueba.mx/api')).toBe(
      'https://api.prueba.mx/api/stream',
    )
    expect(construirUrlStream('https://api.prueba.mx/api', '')).toBe(
      'https://api.prueba.mx/api/stream',
    )
  })

  it('codifica el token cuando existe', () => {
    expect(
      construirUrlStream('https://api.prueba.mx/api', 'jwt con espacios'),
    ).toBe('https://api.prueba.mx/api/stream?token=jwt%20con%20espacios')
  })
})
