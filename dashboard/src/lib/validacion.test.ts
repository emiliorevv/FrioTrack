import { describe, expect, it } from 'vitest'
import { aNumero, esObjeto } from './validacion'

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

describe('aNumero', () => {
  it('acepta los formatos que produce un input number', () => {
    expect(aNumero('.5')).toBe(0.5)
    expect(aNumero('-.5')).toBe(-0.5)
    expect(aNumero('1e1')).toBe(10)
    expect(aNumero('0')).toBe(0)
  })

  it('rechaza vacío, espacios y valores no finitos', () => {
    expect(aNumero('')).toBeNull()
    expect(aNumero('   ')).toBeNull()
    expect(aNumero('abc')).toBeNull()
    expect(aNumero('Infinity')).toBeNull()
  })
})
