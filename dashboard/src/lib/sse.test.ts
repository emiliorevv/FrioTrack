import { describe, expect, it } from 'vitest'
import { parsearJson } from './sse'

describe('parsearJson', () => {
  it('parsea JSON válido', () => {
    expect(parsearJson('{"camara_id":1,"temperatura_c":3.1}')).toEqual({
      camara_id: 1,
      temperatura_c: 3.1,
    })
  })

  it('devuelve null cuando el texto no es JSON', () => {
    expect(parsearJson('{')).toBeNull()
    expect(parsearJson('')).toBeNull()
  })
})
