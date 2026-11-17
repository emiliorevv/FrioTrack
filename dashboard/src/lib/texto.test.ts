import { describe, expect, it } from 'vitest'
import { normalizarTexto } from './texto'

describe('normalizarTexto', () => {
  it('quita acentos y mayúsculas para buscar', () => {
    expect(normalizarTexto('  Salmón ÁÉÍ  ')).toBe('  salmon aei  ')
  })
})
