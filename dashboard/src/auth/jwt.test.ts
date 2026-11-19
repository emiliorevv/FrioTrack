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
  es_demo: true,
  exp: Math.floor(Date.now() / 1000) + 3600,
}

describe('decodificarJwt', () => {
  it('lee usuario, rol, uid y restaurante_id', () => {
    expect(decodificarJwt(crearToken(base))).toEqual({
      usuario: 'dueno',
      rol: 'dueno',
      uid: 3,
      restaurante_id: 1,
      es_demo: true,
      exp: base.exp,
    })
  })

  it('usa es_demo del claim y no el id del tenant', () => {
    const real = crearToken({ ...base, restaurante_id: 1, es_demo: false })
    const demoEnOtroTenant = crearToken({
      ...base,
      restaurante_id: 2,
      es_demo: true,
    })

    expect(decodificarJwt(real)?.es_demo).toBe(false)
    expect(decodificarJwt(demoEnOtroTenant)?.es_demo).toBe(true)
  })

  it('cae al restaurante demo si el backend viejo no manda es_demo', () => {
    const sinClaim = { ...base } as Record<string, unknown>
    delete sinClaim.es_demo

    expect(decodificarJwt(crearToken(sinClaim))?.es_demo).toBe(true)
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
