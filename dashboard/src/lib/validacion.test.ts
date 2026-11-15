import { describe, expect, it } from 'vitest'
import { esObjeto } from './validacion'

describe('esObjeto', () => {
  it('acepta objetos planos', () => {
    expect(esObjeto({ id: 1 })).toBe(true)
  })

  it('rechaza null, primitivos y arreglos', () => {
    expect(esObjeto(null)).toBe(false)
    expect(esObjeto('texto')).toBe(false)
    expect(esObjeto(7)).toBe(false)
    expect(esObjeto([1, 2])).toBe(false)
  })
})
