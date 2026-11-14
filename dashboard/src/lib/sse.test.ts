import { describe, expect, it } from 'vitest'
import { esObjeto, parsearJson } from './sse'

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

describe('esObjeto', () => {
  it('acepta objetos planos', () => {
    expect(esObjeto({ id: 1 })).toBe(true)
    expect(esObjeto(parsearJson('{"id":1}'))).toBe(true)
  })

  it('rechaza null, primitivos y arreglos', () => {
    expect(esObjeto(null)).toBe(false)
    expect(esObjeto('texto')).toBe(false)
    expect(esObjeto(7)).toBe(false)
    expect(esObjeto([1, 2])).toBe(false)
  })
})
