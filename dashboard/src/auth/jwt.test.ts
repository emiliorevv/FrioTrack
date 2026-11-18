import { describe, expect, it } from 'vitest'
import { decodificarJwt } from './jwt'

function crearToken(payload: Record<string, unknown>): string {
  const codificado = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `cabecera.${codificado}.firma`
}

const base = {
  sub: 'dueno',
  uid: 3,
  rol: 'dueno',
  restaurante_id: 1,
  exp: Math.floor(Date.now() / 1000) + 3600,
}

describe('decodificarJwt', () => {
  it('lee usuario, rol, uid y restaurante_id', () => {
    expect(decodificarJwt(crearToken(base))).toEqual({
      usuario: 'dueno',
      rol: 'dueno',
      uid: 3,
      restaurante_id: 1,
      exp: base.exp,
    })
  })

  it('marca el restaurante demo con id 1', () => {
    expect(decodificarJwt(crearToken(base))?.restaurante_id).toBe(1)
  })

  it.each([
    ['ausente', undefined],
    ['cero', 0],
    ['negativo', -1],
    ['decimal', 1.5],
    ['texto', '1'],
  ])('rechaza un restaurante_id %s', (_caso, valor) => {
    const payload = { ...base, restaurante_id: valor }
    expect(decodificarJwt(crearToken(payload))).toBeNull()
  })
})
