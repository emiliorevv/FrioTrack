import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  construirUrlStream,
  RECONEXION_BASE_MS,
  RECONEXION_MAX_MS,
  retrasoReconexion,
} from './stream'

afterEach(() => {
  vi.restoreAllMocks()
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

describe('retrasoReconexion', () => {
  it('crece 5, 10, 20 y se queda en el tope de 30 s', () => {
    expect(retrasoReconexion(0, 0.5)).toBe(RECONEXION_BASE_MS)
    expect(retrasoReconexion(1, 0.5)).toBe(10_000)
    expect(retrasoReconexion(2, 0.5)).toBe(20_000)
    expect(retrasoReconexion(3, 0.5)).toBe(RECONEXION_MAX_MS)
    expect(retrasoReconexion(8, 0.5)).toBe(RECONEXION_MAX_MS)
  })

  it('aplica un jitter de ±25 %', () => {
    expect(retrasoReconexion(0, 0)).toBe(3_750)
    expect(retrasoReconexion(0, 1)).toBe(6_250)
  })
})
