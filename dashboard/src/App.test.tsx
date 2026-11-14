import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
} from './api/client'
import App from './App'
import type { Camara, Kpis, Lectura } from './types'

vi.mock('./api/client', () => ({
  obtenerHealth: vi.fn(),
  obtenerCamaras: vi.fn(),
  obtenerKpis: vi.fn(),
  obtenerLecturas: vi.fn(),
}))

const kpis: Kpis = {
  pct_tiempo_en_rango_24h: 97.3,
  alertas_activas: 1,
  tiempo_respuesta_promedio_min: 6.5,
  valor_en_riesgo_mxn: 4850,
  merma_hoy_mxn: 0,
  merma_mes_mxn: 1720,
}

function crearCamaras(): Camara[] {
  const ahora = new Date().toISOString()

  return [
    {
      id: 1,
      nombre: 'Pescados y mariscos',
      rango_min_c: 0,
      rango_max_c: 2,
      min_para_riesgo: 10,
      min_para_merma: 60,
      estado: 'critica',
      ultima_lectura: {
        ts: ahora,
        temperatura_c: 3.1,
        humedad_pct: 85,
        puerta_abierta: true,
      },
      valor_en_riesgo_mxn: 4850,
    },
    {
      id: 2,
      nombre: 'Carnes y aves',
      rango_min_c: 0,
      rango_max_c: 4,
      min_para_riesgo: 15,
      min_para_merma: 120,
      estado: 'en_rango',
      ultima_lectura: {
        ts: ahora,
        temperatura_c: 2.5,
        humedad_pct: 80,
        puerta_abierta: false,
      },
      valor_en_riesgo_mxn: 0,
    },
    {
      id: 3,
      nombre: 'Lácteos',
      rango_min_c: 1,
      rango_max_c: 4,
      min_para_riesgo: 20,
      min_para_merma: 180,
      estado: 'en_rango',
      ultima_lectura: {
        ts: ahora,
        temperatura_c: 2.2,
        humedad_pct: 80,
        puerta_abierta: false,
      },
      valor_en_riesgo_mxn: 0,
    },
    {
      id: 4,
      nombre: 'Verduras y frutas',
      rango_min_c: 4,
      rango_max_c: 8,
      min_para_riesgo: 30,
      min_para_merma: 240,
      estado: 'en_rango',
      ultima_lectura: {
        ts: ahora,
        temperatura_c: 5.8,
        humedad_pct: 80,
        puerta_abierta: false,
      },
      valor_en_riesgo_mxn: 0,
    },
    {
      id: 5,
      nombre: 'Congelador',
      rango_min_c: -22,
      rango_max_c: -18,
      min_para_riesgo: 20,
      min_para_merma: 120,
      estado: 'en_rango',
      ultima_lectura: {
        ts: ahora,
        temperatura_c: -19.8,
        humedad_pct: 80,
        puerta_abierta: false,
      },
      valor_en_riesgo_mxn: 0,
    },
  ]
}

function crearSerie(camaraId: number): Lectura[] {
  const ahora = new Date().toISOString()

  return [1, 2, 3].map((indice) => ({
    id: camaraId * 10 + indice,
    ts: ahora,
    recibida_en: ahora,
    temperatura_c: 1 + camaraId * 0.1 + indice * 0.01,
    humedad_pct: 80,
    puerta_abierta: false,
    sospechosa: false,
  }))
}

beforeEach(() => {
  window.localStorage.clear()
  vi.mocked(obtenerHealth).mockResolvedValue({ ok: true, escala_tiempo: 30 })
  vi.mocked(obtenerCamaras).mockResolvedValue(crearCamaras())
  vi.mocked(obtenerKpis).mockResolvedValue(kpis)
  vi.mocked(obtenerLecturas).mockImplementation(async (id) => crearSerie(id))
})

describe('vista general', () => {
  it('muestra los KPIs y las cinco cámaras de la API', async () => {
    render(<App />)

    expect(await screen.findAllByRole('article')).toHaveLength(5)
    expect(screen.getByText('97.3%')).toBeInTheDocument()
    expect(screen.getByText('6.5 min')).toBeInTheDocument()
    expect(screen.getByText('Alertas activas')).toBeInTheDocument()
    expect(screen.getByText('Valor en riesgo')).toBeInTheDocument()
    expect(screen.getByText('$1,720')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', {
        level: 3,
        name: 'Pescados y mariscos',
      }),
    ).toBeInTheDocument()
  })

  it('muestra la etiqueta de modo demo con la escala de /health', async () => {
    render(<App />)

    expect(await screen.findByText('MODO DEMO ×30')).toBeInTheDocument()
  })

  it('el filtro Crítica deja solo Pescados y mariscos y Alerta queda vacío', async () => {
    render(<App />)
    await screen.findAllByRole('article')

    const chipAlerta = screen.getByRole('button', { name: 'Alerta (0)' })
    const chipCritica = screen.getByRole('button', { name: 'Crítica (1)' })
    expect(chipCritica).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(chipCritica)

    expect(chipCritica).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(
      screen.getByRole('article', { name: 'Pescados y mariscos' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('article', { name: 'Carnes y aves' }),
    ).not.toBeInTheDocument()

    fireEvent.click(chipAlerta)

    expect(chipAlerta).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryAllByRole('article')).toHaveLength(0)
    expect(
      screen.getByText('No hay cámaras que coincidan con el filtro.'),
    ).toBeInTheDocument()
  })

  it('la búsqueda congelador deja solo el Congelador', async () => {
    render(<App />)
    await screen.findAllByRole('article')

    fireEvent.change(screen.getByLabelText('Buscar cámara'), {
      target: { value: 'congelador' },
    })

    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(
      screen.getByRole('article', { name: 'Congelador' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('article', { name: 'Pescados y mariscos' }),
    ).not.toBeInTheDocument()
  })

  it('el banner de onboarding se puede cerrar', async () => {
    render(<App />)
    await screen.findAllByRole('article')

    expect(
      screen.getByText(
        'FríoTrack vigila tus cámaras. Si algo sale de rango, te avisa en el dashboard.',
      ),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar aviso' }))

    expect(
      screen.queryByText(/FríoTrack vigila tus cámaras/),
    ).not.toBeInTheDocument()
  })

  it('el estado crítico se anuncia en texto y con estilo propio', async () => {
    render(<App />)
    await screen.findAllByRole('article')

    const pescados = screen.getByRole('article', {
      name: 'Pescados y mariscos',
    })

    expect(pescados).toHaveClass('camera-card--critica')
    expect(within(pescados).getByText('Crítica')).toBeInTheDocument()
    expect(within(pescados).getByText('Abierta')).toBeInTheDocument()
    expect(within(pescados).getByText('$4,850')).toBeInTheDocument()
  })

  it('muestra datos en vivo y avisa que el SIEM usa ejemplos', async () => {
    render(<App />)
    await screen.findAllByRole('article')

    expect(screen.getByText('Datos en vivo · FríoTrack')).toBeInTheDocument()
    expect(screen.queryByText(/Datos simulados/)).not.toBeInTheDocument()
    expect(screen.getByText(/Datos de ejemplo/)).toBeInTheDocument()
    expect(
      screen.getAllByText(/Actualizado hace \d+ s/).length,
    ).toBeGreaterThan(0)
  })

  it('muestra el skeleton mientras no llega la primera respuesta', () => {
    vi.mocked(obtenerHealth).mockReturnValue(new Promise<never>(() => {}))
    vi.mocked(obtenerCamaras).mockReturnValue(new Promise<never>(() => {}))
    vi.mocked(obtenerKpis).mockReturnValue(new Promise<never>(() => {}))

    const { container } = render(<App />)

    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      'Cargando datos del dashboard',
    )
  })

  it('muestra el error y lo resuelve al pulsar Reintentar', async () => {
    vi.mocked(obtenerCamaras).mockRejectedValueOnce(
      new Error('La API no responde'),
    )

    render(<App />)

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('No se pudo cargar el dashboard')
    expect(alerta).toHaveTextContent('La API no responde')

    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))

    expect(await screen.findAllByRole('article')).toHaveLength(5)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
