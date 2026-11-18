import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  atenderAlerta,
  crearLote,
  listarSensores,
  obtenerAlertasActivas,
  obtenerAlertasSeguridad,
  obtenerCamaras,
  obtenerHealth,
  obtenerKpis,
  obtenerLecturas,
  obtenerLotes,
} from './api/client'
import App from './App'
import { useStreamEvent } from './realtime/StreamProvider'
import type {
  AlertaOperativa,
  AlertaSeguridad,
  Camara,
  Kpis,
  Lectura,
} from './types'

vi.mock('./api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('./api/client')>()
  return {
    ...original,
    atenderAlerta: vi.fn(),
    obtenerAlertasActivas: vi.fn(),
    obtenerAlertasSeguridad: vi.fn(),
    obtenerHealth: vi.fn(),
    obtenerCamaras: vi.fn(),
    obtenerKpis: vi.fn(),
    obtenerLecturas: vi.fn(),
    crearCamara: vi.fn(),
    actualizarCamara: vi.fn(),
    eliminarCamara: vi.fn(),
    listarSensores: vi.fn(),
    crearSensor: vi.fn(),
    rotarTokenSensor: vi.fn(),
    actualizarSensor: vi.fn(),
    eliminarSensor: vi.fn(),
    obtenerLotes: vi.fn(),
    crearLote: vi.fn(),
    actualizarLote: vi.fn(),
    eliminarLote: vi.fn(),
    marcarLoteMerma: vi.fn(),
    simularFalla: vi.fn(),
    simularPuerta: vi.fn(),
    simularAtaque: vi.fn(),
    recuperarDemo: vi.fn(),
  }
})

vi.mock('./realtime/StreamProvider', () => ({
  useStreamEvent: vi.fn(),
  useStreamReconexion: vi.fn(() => 0),
}))

const onLogout = vi.fn()

function renderizarApp(
  props: Partial<{
    usuario: string
    rol: string
    esDemo: boolean
    onLogout: () => void
  }> = {},
) {
  return render(
    <App usuario="jefe" rol="jefe_cocina" onLogout={onLogout} {...props} />,
  )
}

type Oyente = (evento: MessageEvent<string>) => void

const oyentes = new Map<string, Oyente>()

const kpis: Kpis = {
  pct_tiempo_en_rango_24h: 97.3,
  alertas_activas: 1,
  tiempo_respuesta_promedio_min: 6.5,
  valor_en_riesgo_mxn: 4850,
  merma_hoy_mxn: 0,
  merma_mes_mxn: 1720,
}

const alertaSeguridad: AlertaSeguridad = {
  id: 1,
  regla_id: '3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41',
  regla: 'Fuerza bruta de tokens en ingesta de telemetría y cron',
  severidad: 'high',
  ts: new Date().toISOString(),
  ip_origen: '192.168.0.4',
  detalle: {
    clave: 'ip:192.168.0.4',
    rutas: ['/api/telemetria'],
    intentos: 15,
    ventana_s: 300,
  },
  accion: 'bloquear_ip',
}

const alertaOperativa: AlertaOperativa = {
  id: 31,
  camara_id: 1,
  tipo: 'temperatura',
  abierta_en: new Date().toISOString(),
  cerrada_en: null,
  atendida_por: null,
  temperatura_max_c: 3.4,
  sms_enviados: 1,
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
      valor_inventario_mxn: 12340,
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
      valor_inventario_mxn: 0,
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
      valor_inventario_mxn: 0,
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
      valor_inventario_mxn: 0,
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
      valor_inventario_mxn: 0,
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
  vi.clearAllMocks()
  oyentes.clear()
  window.localStorage.clear()
  vi.mocked(useStreamEvent).mockImplementation((evento, oyente) => {
    oyentes.set(evento, oyente)
  })
  vi.mocked(obtenerHealth).mockResolvedValue({ ok: true, escala_tiempo: 30 })
  vi.mocked(obtenerCamaras).mockResolvedValue(crearCamaras())
  vi.mocked(listarSensores).mockResolvedValue([])
  vi.mocked(obtenerLotes).mockResolvedValue([])
  vi.mocked(obtenerKpis).mockResolvedValue(kpis)
  vi.mocked(obtenerAlertasSeguridad).mockResolvedValue([alertaSeguridad])
  vi.mocked(obtenerAlertasActivas).mockResolvedValue([alertaOperativa])
  vi.mocked(atenderAlerta).mockResolvedValue({
    ...alertaOperativa,
    atendida_por: 3,
  })
  vi.mocked(obtenerLecturas).mockImplementation(async (id) => crearSerie(id))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('vista general', () => {
  it('muestra los KPIs y las cinco cámaras de la API', async () => {
    renderizarApp()

    expect(await screen.findAllByRole('article')).toHaveLength(5)
    expect(screen.getByText('97.3%')).toBeInTheDocument()
    expect(screen.getByText('6.5 min')).toBeInTheDocument()
    expect(screen.getAllByText('Alertas activas').length).toBeGreaterThan(0)
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
    renderizarApp()

    expect(await screen.findByText('MODO DEMO ×30')).toBeInTheDocument()
  })

  it('explica qué es el resumen de hoy al abrir el detalle', async () => {
    renderizarApp()
    await screen.findAllByRole('article')

    const resumen = screen.getByText('¿Qué es esto?')
    const details = resumen.closest('details')
    expect(details).not.toBeNull()
    expect(details).not.toHaveAttribute('open')

    fireEvent.click(resumen)

    expect(details).toHaveAttribute('open')
    expect(
      screen.getByText(/El % en rango cubre las últimas 24 horas/),
    ).toBeInTheDocument()
  })

  it('el filtro Crítica deja solo Pescados y mariscos y Alerta queda vacío', async () => {
    renderizarApp()
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
    renderizarApp()
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
    renderizarApp()
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

  it('muestra la bienvenida y el botón abre el formulario de cámara para el dueño', async () => {
    vi.mocked(obtenerCamaras).mockResolvedValueOnce([])

    renderizarApp({ usuario: 'dueno-nuevo', rol: 'dueno' })

    expect(
      await screen.findByRole('heading', {
        name: 'Tu restaurante está listo',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Aún no tienes cámaras. El siguiente paso es agregar la primera y conectar su sensor.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Crea tu restaurante')).toBeInTheDocument()
    expect(screen.getByText('Agrega una cámara')).toBeInTheDocument()
    expect(screen.getByText('Conecta el sensor')).toBeInTheDocument()
    expect(screen.getByText('Completado')).toBeInTheDocument()
    expect(screen.getByText('Siguiente')).toBeInTheDocument()
    expect(screen.getByText('Después')).toBeInTheDocument()

    const boton = screen.getByRole('button', { name: 'Agregar cámara' })
    expect(boton).toBeEnabled()
    expect(
      screen.getByText('Se abrirá el formulario para crear la primera cámara.'),
    ).toBeInTheDocument()

    fireEvent.click(boton)

    expect(
      await screen.findByRole('dialog', { name: 'Nueva cámara' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Nombre de la cámara')).toHaveFocus()

    expect(
      screen.queryByText(/FríoTrack vigila tus cámaras/),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText('Todavía no hay cámaras registradas.'),
    ).not.toBeInTheDocument()
    expect(screen.getByText('Aquí aparecerán tus cámaras.')).toBeInTheDocument()
  })

  it('no muestra la bienvenida cuando el restaurante ya tiene cámaras', async () => {
    renderizarApp({ usuario: 'dueno-nuevo', rol: 'dueno' })
    await screen.findAllByRole('article')

    expect(
      screen.queryByRole('heading', { name: 'Tu restaurante está listo' }),
    ).not.toBeInTheDocument()
  })

  it.each(['jefe_cocina', 'gerente'] as const)(
    'no muestra el onboarding de dueño a un %s sin cámaras',
    async (rol) => {
      vi.mocked(obtenerCamaras).mockResolvedValueOnce([])

      renderizarApp({ usuario: 'persona', rol })

      expect(
        await screen.findByText('Aquí aparecerán tus cámaras.'),
      ).toBeInTheDocument()
      expect(
        screen.queryByRole('heading', { name: 'Tu restaurante está listo' }),
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: 'Agregar cámara' }),
      ).not.toBeInTheDocument()
    },
  )

  it('mantiene la bienvenida si falla un refresco del resumen', async () => {
    vi.mocked(obtenerCamaras).mockResolvedValueOnce([])
    renderizarApp({ usuario: 'dueno-nuevo', rol: 'dueno' })

    expect(
      await screen.findByRole('heading', {
        name: 'Tu restaurante está listo',
      }),
    ).toBeInTheDocument()

    vi.mocked(obtenerCamaras).mockRejectedValueOnce(new Error('sin red'))
    vi.useFakeTimers()

    act(() => {
      oyentes.get('alerta_abierta')?.(
        new MessageEvent('alerta_abierta', { data: '{"id":1}' }),
      )
    })
    await act(async () => {
      vi.advanceTimersByTime(500)
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(
      screen.getByRole('heading', { name: 'Tu restaurante está listo' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/No se pudo actualizar el resumen HTTP/),
    ).toBeInTheDocument()
  })

  it('el dueño ve su rol y puede atender alertas', async () => {
    renderizarApp({ usuario: 'dueno-nuevo', rol: 'dueno' })
    await screen.findAllByRole('article')

    expect(screen.getByText('Dueño')).toBeInTheDocument()

    const seccion = screen.getByRole('region', { name: /Alertas activas/ })
    expect(
      await within(seccion).findByRole('button', { name: 'Atender' }),
    ).toBeEnabled()
  })

  it('el estado crítico se anuncia en texto y con estilo propio', async () => {
    renderizarApp()
    await screen.findAllByRole('article')

    const pescados = screen.getByRole('article', {
      name: 'Pescados y mariscos',
    })

    expect(pescados).toHaveClass('camera-card--critica')
    expect(within(pescados).getByText('Crítica')).toBeInTheDocument()
    expect(within(pescados).getByText('Abierta')).toBeInTheDocument()
    expect(within(pescados).getByText('$4,850')).toBeInTheDocument()
    expect(within(pescados).getByText('Inventario')).toBeInTheDocument()
    expect(within(pescados).getByText('$12,340')).toBeInTheDocument()
  })

  it('muestra datos en vivo y la alerta real del detector', async () => {
    renderizarApp()
    await screen.findAllByRole('article')

    expect(screen.getByText('Datos en vivo · FríoTrack')).toBeInTheDocument()
    expect(screen.queryByText(/Datos simulados/)).not.toBeInTheDocument()
    expect(
      await screen.findByText(
        'Fuerza bruta de tokens en ingesta de telemetría y cron',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Alta')).toBeInTheDocument()
    expect(screen.getByText('192.168.0.4 · IP bloqueada')).toBeInTheDocument()
    fireEvent.click(screen.getByText('¿Qué pasó?'))
    expect(
      screen.getByText(/Detectamos muchos intentos rechazados/),
    ).toBeInTheDocument()
    expect(screen.queryByText(/Datos de ejemplo/)).not.toBeInTheDocument()
    expect(
      screen.getAllByText(/Actualizado hace \d+ s/).length,
    ).toBeGreaterThan(0)
  })

  it('muestra el estado vacío del panel de seguridad', async () => {
    vi.mocked(obtenerAlertasSeguridad).mockResolvedValueOnce([])

    renderizarApp()
    await screen.findAllByRole('article')

    expect(
      await screen.findByText('Sin alertas del detector.'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/Datos de ejemplo/)).not.toBeInTheDocument()
  })

  it('muestra la sección de alertas activas con la alerta de la API', async () => {
    renderizarApp()
    await screen.findAllByRole('article')

    const seccion = screen.getByRole('region', { name: /Alertas activas/ })
    expect(
      await within(seccion).findByRole('button', { name: 'Atender' }),
    ).toBeEnabled()
    expect(within(seccion).getByText('Pescados y mariscos')).toBeInTheDocument()
    expect(within(seccion).getByText('Temperatura')).toBeInTheDocument()
    expect(within(seccion).getByText(/Máx\. 3\.4 °C/)).toBeInTheDocument()
  })

  it('atiende desde la sección y marca la alerta como atendida', async () => {
    renderizarApp()
    await screen.findAllByRole('article')

    const seccion = screen.getByRole('region', { name: /Alertas activas/ })
    fireEvent.click(
      await within(seccion).findByRole('button', { name: 'Atender' }),
    )

    await waitFor(() => {
      expect(
        within(seccion).getByRole('button', { name: 'Atendida' }),
      ).toBeDisabled()
    })
    expect(atenderAlerta).toHaveBeenCalledWith(31, undefined)
  })

  it('muestra el estado vacío de alertas activas', async () => {
    vi.mocked(obtenerAlertasActivas).mockResolvedValueOnce([])

    renderizarApp()
    await screen.findAllByRole('article')

    expect(await screen.findByText('Sin alertas activas')).toBeInTheDocument()
  })

  it('muestra la sesión y permite cerrar sesión', async () => {
    renderizarApp()
    await screen.findAllByRole('article')

    expect(screen.getByText('jefe')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Salir' }))

    expect(onLogout).toHaveBeenCalledTimes(1)
  })

  it('el gerente no puede atender alertas', async () => {
    renderizarApp({ usuario: 'gerente', rol: 'gerente' })
    await screen.findAllByRole('article')

    const seccion = screen.getByRole('region', { name: /Alertas activas/ })
    const boton = await within(seccion).findByRole('button', {
      name: 'Atender',
    })
    expect(boton).toBeDisabled()
    expect(
      within(seccion).getByText('Solo jefe de cocina puede atender.'),
    ).toBeInTheDocument()
  })

  it('muestra el skeleton mientras no llega la primera respuesta', () => {
    vi.mocked(obtenerHealth).mockReturnValue(new Promise<never>(() => {}))
    vi.mocked(obtenerCamaras).mockReturnValue(new Promise<never>(() => {}))
    vi.mocked(obtenerKpis).mockReturnValue(new Promise<never>(() => {}))

    const { container } = renderizarApp()

    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      'Cargando datos del dashboard',
    )
    expect(screen.getByText('Sin datos')).toBeInTheDocument()
    expect(screen.queryByText(/Actualizado hace/)).not.toBeInTheDocument()
    expect(screen.getByText('Conectando · FríoTrack')).toBeInTheDocument()
  })

  it('muestra el error, deshabilita Reintentar mientras reintenta y luego pinta los datos', async () => {
    vi.mocked(obtenerCamaras).mockRejectedValueOnce(
      new Error('La API no responde'),
    )

    renderizarApp()

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('No se pudo cargar el dashboard')
    expect(alerta).toHaveTextContent('La API no responde')
    expect(screen.getByText('Sin datos')).toBeInTheDocument()
    expect(screen.getByText('Sin conexión · FríoTrack')).toBeInTheDocument()

    let resolver!: (camaras: Camara[]) => void
    vi.mocked(obtenerCamaras).mockReturnValueOnce(
      new Promise<Camara[]>((resolverCamaras) => {
        resolver = resolverCamaras
      }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))

    const reintentando = screen.getByRole('button', {
      name: 'Reintentando…',
    })
    expect(reintentando).toBeDisabled()
    expect(reintentando).toHaveAttribute('aria-busy', 'true')

    await act(async () => {
      resolver(crearCamaras())
    })

    expect(await screen.findAllByRole('article')).toHaveLength(5)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('avisa de un refresco fallido sin ocultar los datos', async () => {
    renderizarApp()
    await screen.findAllByRole('article')
    expect(screen.getByText('Datos en vivo · FríoTrack')).toBeInTheDocument()

    vi.mocked(obtenerCamaras).mockRejectedValueOnce(new Error('sin red'))
    vi.useFakeTimers()

    act(() => {
      oyentes.get('alerta_abierta')?.(
        new MessageEvent('alerta_abierta', { data: '{"id":1}' }),
      )
    })
    await act(async () => {
      vi.advanceTimersByTime(500)
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getAllByRole('article')).toHaveLength(5)
    expect(
      screen.getByText(
        /No se pudo actualizar el resumen HTTP; los eventos en vivo siguen llegando/,
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('sin red')).toBeInTheDocument()
    expect(screen.getByText('Datos en vivo · FríoTrack')).toBeInTheDocument()
    expect(
      screen.queryByText('Datos desactualizados · FríoTrack'),
    ).not.toBeInTheDocument()
  })

  it('muestra la sección Inventario para cualquier rol', async () => {
    renderizarApp({ usuario: 'gerente', rol: 'gerente' })

    expect(
      await screen.findByRole('heading', { name: 'Inventario' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Agregar lote' }),
    ).not.toBeInTheDocument()
  })

  it('refresca KPIs y cámaras después de crear un lote', async () => {
    renderizarApp({ usuario: 'dueno-nuevo', rol: 'dueno' })
    await screen.findAllByRole('article')
    vi.mocked(crearLote).mockResolvedValue(null)

    fireEvent.click(await screen.findByRole('button', { name: 'Agregar lote' }))
    const dialogo = screen.getByRole('dialog', { name: 'Nuevo lote' })
    fireEvent.change(within(dialogo).getByLabelText('Producto'), {
      target: { value: 'Salmón fresco' },
    })
    fireEvent.change(within(dialogo).getByLabelText('Cámara'), {
      target: { value: '1' },
    })
    fireEvent.change(within(dialogo).getByLabelText('Cantidad'), {
      target: { value: '2.5' },
    })
    fireEvent.change(within(dialogo).getByLabelText('Costo total (MXN)'), {
      target: { value: '450.50' },
    })
    fireEvent.change(within(dialogo).getByLabelText('Caducidad'), {
      target: { value: '2026-12-31' },
    })
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar lote' }),
    )

    await waitFor(() => expect(obtenerKpis).toHaveBeenCalledTimes(2))
    expect(obtenerCamaras).toHaveBeenCalledTimes(2)
    expect(
      screen.queryByRole('dialog', { name: 'Nuevo lote' }),
    ).not.toBeInTheDocument()
  })

  it('refresca inventario al recibir el evento SSE lote_actualizado', async () => {
    renderizarApp()
    await screen.findAllByRole('article')
    await waitFor(() => expect(obtenerLotes).toHaveBeenCalledTimes(1))

    act(() => {
      oyentes.get('lote_actualizado')?.(
        new MessageEvent('lote_actualizado', { data: '{}' }),
      )
    })

    await waitFor(() => expect(obtenerLotes).toHaveBeenCalledTimes(2))
  })

  it('no muestra el panel demo fuera del tenant demo', async () => {
    renderizarApp({ usuario: 'dueno', rol: 'dueno', esDemo: false })
    await screen.findAllByRole('article')

    expect(
      screen.queryByRole('button', { name: 'Abrir panel de demo' }),
    ).not.toBeInTheDocument()
  })

  it('muestra el panel demo al dueño del tenant demo', async () => {
    renderizarApp({ usuario: 'dueno', rol: 'dueno', esDemo: true })
    await screen.findAllByRole('article')

    fireEvent.click(screen.getByRole('button', { name: 'Abrir panel de demo' }))

    expect(
      screen.getByRole('dialog', { name: 'Panel de demo' }),
    ).toBeInTheDocument()
  })

  it('muestra el panel demo al jefe de cocina del tenant demo', async () => {
    renderizarApp({
      usuario: 'jefe',
      rol: 'jefe_cocina',
      esDemo: true,
    })
    await screen.findAllByRole('article')

    expect(
      screen.getByRole('button', { name: 'Abrir panel de demo' }),
    ).toBeInTheDocument()
  })

  it('no muestra el panel demo al gerente del tenant demo', async () => {
    renderizarApp({ usuario: 'gerente', rol: 'gerente', esDemo: true })
    await screen.findAllByRole('article')

    expect(
      screen.queryByRole('button', { name: 'Abrir panel de demo' }),
    ).not.toBeInTheDocument()
  })
})
