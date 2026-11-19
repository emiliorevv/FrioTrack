import { describe, expect, it } from 'vitest'
import {
  esTiempoReglaSingular,
  formatearSegundosRegla,
  formatearSegundosReglaLarga,
} from './format'

describe('formato de la escala demo', () => {
  it('usa enteros o un decimal para segundos', () => {
    expect(formatearSegundosRegla(60 / 30)).toBe('2 s')
    expect(formatearSegundosRegla(60 / 24)).toBe('2.5 s')
    expect(formatearSegundosRegla(60 / 2)).toBe('30 s')
  })

  it('nunca muestra 0 s con escalas grandes', () => {
    expect(formatearSegundosRegla(60 / 3600)).toBe('17 ms')
    expect(formatearSegundosRegla(1 / 2)).toBe('500 ms')
  })

  it('formatea la explicación larga con singular correcto', () => {
    expect(formatearSegundosReglaLarga(60 / 60)).toBe('1 segundo')
    expect(formatearSegundosReglaLarga(60 / 30)).toBe('2 segundos')
    expect(formatearSegundosReglaLarga(60 / 3600)).toBe('17 milisegundos')
    expect(esTiempoReglaSingular(60 / 60)).toBe(true)
    expect(esTiempoReglaSingular(60 / 30)).toBe(false)
  })
})
