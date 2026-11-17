import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  actualizarLote,
  crearLote,
  eliminarLote,
  ErrorApi,
  marcarLoteMerma,
  obtenerLotes,
} from '../api/client'
import { ETIQUETA_ESTADO_LOTE } from '../lib/format'
import type { Camara, Lote } from '../types'
import { Inventario } from './Inventario'

vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>()
  return {
    ...original,
    obtenerLotes: vi.fn(),
    crearLote: vi.fn(),
    actualizarLote: vi.fn(),
    eliminarLote: vi.fn(),
    marcarLoteMerma: vi.fn(),
  }
})

const camaras: Camara[] = [
  {
    id: 1,
    nombre: 'Pescados y mariscos',
    rango_min_c: 0,
    rango_max_c: 2,
    min_para_riesgo: 10,
    min_para_merma: 60,
    estado: 'en_rango',
    ultima_lectura: null,
    valor_en_riesgo_mxn: 0,
    valor_inventario_mxn: 0,
  },
  {
    id: 2,
    nombre: 'Carnes y aves',
    rango_min_c: 0,
    rango_max_c: 4,
    min_para_riesgo: 15,
    min_para_merma: 120,
    estado: 'en_rango',
    ultima_lectura: null,
    valor_en_riesgo_mxn: 0,
    valor_inventario_mxn: 0,
  },
]

const salmon: Lote = {
  id: 1,
  producto: 'Salmón fresco',
  camara_id: 1,
  cantidad: 2.5,
  unidad: 'kg',
  costo_total_mxn: 450.5,
  caducidad: '2030-01-01',
  estado: 'ok',
  merma_en: null,
}

const leche: Lote = {
  id: 2,
  producto: 'Leche entera',
  camara_id: 2,
  cantidad: 10,
  unidad: 'l',
  costo_total_mxn: 250,
  caducidad: '2020-01-01',
  estado: 'en_riesgo',
  merma_en: null,
}

const queso: Lote = {
  id: 3,
  producto: 'Queso añejo',
  camara_id: 1,
  cantidad: 1,
  unidad: 'kg',
  costo_total_mxn: 100,
  caducidad: '2030-06-01',
  estado: 'merma',
  merma_en: '2026-11-16T18:00:00.000Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(obtenerLotes).mockResolvedValue([salmon, leche, queso])
})

function renderizar(rol = 'dueno', onCambio = vi.fn()) {
  const utilidades = render(
    <Inventario rol={rol} camaras={camaras} onCambio={onCambio} />,
  )
  return { onCambio, ...utilidades }
}

async function esperarLotes() {
  await screen.findByRole('heading', { name: 'Inventario' })
  await screen.findByText('Salmón fresco')
}

function abrirFormularioNuevo() {
  fireEvent.click(screen.getByRole('button', { name: 'Agregar lote' }))
  return screen.getByRole('dialog', { name: 'Nuevo lote' })
}

function llenarFormulario(
  dialogo: HTMLElement,
  valores: {
    producto?: string
    camara?: string
    cantidad?: string
    costo?: string
    caducidad?: string
  } = {},
) {
  const {
    producto = 'Salmón fresco',
    camara = '1',
    cantidad = '2.5',
    costo = '450.50',
    caducidad = '2030-01-01',
  } = valores

  fireEvent.change(within(dialogo).getByLabelText('Producto'), {
    target: { value: producto },
  })
  fireEvent.change(within(dialogo).getByLabelText('Cámara'), {
    target: { value: camara },
  })
  fireEvent.change(within(dialogo).getByLabelText('Cantidad'), {
    target: { value: cantidad },
  })
  fireEvent.change(within(dialogo).getByLabelText('Costo total (MXN)'), {
    target: { value: costo },
  })
  fireEvent.change(within(dialogo).getByLabelText('Caducidad'), {
    target: { value: caducidad },
  })
}

describe('Inventario', () => {
  it('muestra lotes, cámara, cantidades, costos, caducidad y estados', async () => {
    renderizar()
    await esperarLotes()

    const titulo = screen.getByRole('heading', { name: 'Inventario' })
    expect(titulo).toBeInTheDocument()
    expect(screen.getByText(/en 2 lotes activos/)).toBeInTheDocument()
    expect(screen.getByText(/\$700\.50/)).toBeInTheDocument()
    expect(screen.getAllByText('Pescados y mariscos').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Carnes y aves').length).toBeGreaterThan(0)
    expect(screen.getByText('2.5 kg')).toBeInTheDocument()
    expect(screen.getByText('$450.50')).toBeInTheDocument()
    expect(screen.getAllByText('Ok').length).toBeGreaterThan(0)
    expect(screen.getAllByText('En riesgo').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Merma').length).toBeGreaterThan(0)
    expect(screen.getByText('Vencido')).toBeInTheDocument()
    expect(screen.getByText('Queso añejo')).toBeInTheDocument()
  })

  it('filtra por producto, cámara y estado', async () => {
    renderizar()
    await esperarLotes()

    fireEvent.change(screen.getByLabelText('Buscar producto'), {
      target: { value: 'leche' },
    })
    expect(screen.getByText('Leche entera')).toBeInTheDocument()
    expect(screen.queryByText('Salmón fresco')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Buscar producto'), {
      target: { value: '' },
    })
    fireEvent.change(screen.getByLabelText('Cámara'), {
      target: { value: '1' },
    })
    expect(screen.getByText('Salmón fresco')).toBeInTheDocument()
    expect(screen.getByText('Queso añejo')).toBeInTheDocument()
    expect(screen.queryByText('Leche entera')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Estado'), {
      target: { value: 'merma' },
    })
    expect(screen.getByText('Queso añejo')).toBeInTheDocument()
    expect(screen.queryByText('Salmón fresco')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Cámara'), {
      target: { value: '2' },
    })
    expect(
      screen.getByText('No hay lotes que coincidan con los filtros.'),
    ).toBeInTheDocument()
  })

  it('muestra el vacío con acción para quien puede escribir', async () => {
    vi.mocked(obtenerLotes).mockResolvedValue([])
    renderizar('jefe_cocina')

    expect(
      await screen.findByText('No hay lotes registrados.'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Agregar lote' }),
    ).toBeInTheDocument()
  })

  it('muestra el vacío de solo lectura para el gerente', async () => {
    vi.mocked(obtenerLotes).mockResolvedValue([])
    renderizar('gerente')

    expect(
      await screen.findByText('No hay lotes registrados.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Agregar lote' }),
    ).not.toBeInTheDocument()
  })

  it('muestra error y reintenta la carga', async () => {
    vi.mocked(obtenerLotes).mockRejectedValueOnce(
      new ErrorApi('No se pudo cargar el inventario', 500),
    )
    renderizar()

    expect(
      await screen.findByText('No se pudo cargar el inventario'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('No hay lotes registrados.'),
    ).not.toBeInTheDocument()

    vi.mocked(obtenerLotes).mockResolvedValue([salmon])
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))

    expect(await screen.findByText('Salmón fresco')).toBeInTheDocument()
  })

  it('crea un lote y avisa al dashboard', async () => {
    const { onCambio } = renderizar('jefe_cocina')
    await esperarLotes()
    vi.mocked(crearLote).mockResolvedValue(salmon)

    const dialogo = abrirFormularioNuevo()
    llenarFormulario(dialogo)
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar lote' }),
    )

    await waitFor(() =>
      expect(crearLote).toHaveBeenCalledWith({
        producto: 'Salmón fresco',
        camara_id: 1,
        cantidad: 2.5,
        unidad: 'kg',
        costo_total_mxn: 450.5,
        caducidad: '2030-01-01',
      }),
    )
    await waitFor(() => expect(obtenerLotes).toHaveBeenCalledTimes(2))
    expect(onCambio).toHaveBeenCalledTimes(1)
    expect(
      screen.queryByRole('dialog', { name: 'Nuevo lote' }),
    ).not.toBeInTheDocument()
  })

  it('valida producto, cámara, cantidad, costo y caducidad', async () => {
    renderizar()
    await esperarLotes()

    const dialogo = abrirFormularioNuevo()
    llenarFormulario(dialogo, {
      producto: 'X',
      camara: '',
      cantidad: '0',
      costo: '-1',
      caducidad: '',
    })
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar lote' }),
    )

    expect(
      screen.getByText('Escribe un producto de 2 a 120 caracteres.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Selecciona una cámara.')).toBeInTheDocument()
    expect(
      screen.getByText(
        'La cantidad debe ser mayor que 0, con hasta 2 decimales.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('El costo debe ser 0 o más, con hasta 2 decimales.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Escribe una fecha de caducidad válida.'),
    ).toBeInTheDocument()
    expect(crearLote).not.toHaveBeenCalled()
  })

  it('muestra un 422 contextual al crear', async () => {
    renderizar()
    await esperarLotes()
    vi.mocked(crearLote).mockRejectedValue(
      new ErrorApi('La API respondió 422 Unprocessable Entity', 422),
    )

    const dialogo = abrirFormularioNuevo()
    llenarFormulario(dialogo)
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar lote' }),
    )

    expect(
      await screen.findByText(
        'Revisa el producto, la cantidad, el costo y la caducidad.',
      ),
    ).toBeInTheDocument()
  })

  it('edita y mueve un lote a otra cámara', async () => {
    renderizar()
    await esperarLotes()
    vi.mocked(actualizarLote).mockResolvedValue({ ...salmon, camara_id: 2 })

    fireEvent.click(
      screen.getByRole('button', { name: 'Editar lote Salmón fresco' }),
    )
    const dialogo = screen.getByRole('dialog', {
      name: 'Editar Salmón fresco',
    })
    fireEvent.change(within(dialogo).getByLabelText('Cámara'), {
      target: { value: '2' },
    })
    fireEvent.change(within(dialogo).getByLabelText('Cantidad'), {
      target: { value: '3' },
    })
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar lote' }),
    )

    await waitFor(() =>
      expect(actualizarLote).toHaveBeenCalledWith(1, {
        producto: 'Salmón fresco',
        camara_id: 2,
        cantidad: 3,
        unidad: 'kg',
        costo_total_mxn: 450.5,
        caducidad: '2030-01-01',
      }),
    )
  })

  it('marca merma con confirmación y refresca', async () => {
    const { onCambio } = renderizar()
    await esperarLotes()
    vi.mocked(marcarLoteMerma).mockResolvedValue({
      ...salmon,
      estado: 'merma',
      merma_en: '2026-11-16T18:00:00.000Z',
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Marcar merma del lote Salmón fresco',
      }),
    )
    const dialogo = screen.getByRole('dialog', {
      name: 'Marcar merma: Salmón fresco',
    })
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Marcar merma' }),
    )

    await waitFor(() => expect(marcarLoteMerma).toHaveBeenCalledWith(1))
    expect(onCambio).toHaveBeenCalledTimes(1)
    expect(
      screen.queryByRole('dialog', { name: 'Marcar merma: Salmón fresco' }),
    ).not.toBeInTheDocument()
  })

  it('elimina un lote ok y refresca', async () => {
    const { onCambio } = renderizar()
    await esperarLotes()
    vi.mocked(eliminarLote).mockResolvedValue(undefined)

    fireEvent.click(
      screen.getByRole('button', { name: 'Eliminar lote Salmón fresco' }),
    )
    const dialogo = screen.getByRole('dialog', {
      name: 'Eliminar lote: Salmón fresco',
    })
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Eliminar lote' }),
    )

    await waitFor(() => expect(eliminarLote).toHaveBeenCalledWith(1))
    expect(onCambio).toHaveBeenCalledTimes(1)
  })

  it('muestra el 409 al borrar una merma sin cerrar la confirmación', async () => {
    renderizar()
    await esperarLotes()
    const detalle =
      'El lote ya está en merma; no se puede eliminar del historial.'
    vi.mocked(eliminarLote).mockRejectedValue(
      new ErrorApi(detalle, 409, null, detalle),
    )

    fireEvent.click(
      screen.getByRole('button', { name: 'Eliminar lote Salmón fresco' }),
    )
    const dialogo = screen.getByRole('dialog', {
      name: 'Eliminar lote: Salmón fresco',
    })
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Eliminar lote' }),
    )

    expect(await screen.findByText(detalle)).toBeInTheDocument()
    expect(dialogo).toBeInTheDocument()
  })

  it('no cierra la confirmación mientras procesa', async () => {
    renderizar()
    await esperarLotes()
    let resolver!: (valor: Lote | null) => void
    vi.mocked(marcarLoteMerma).mockReturnValue(
      new Promise<Lote | null>((resolve) => {
        resolver = resolve
      }),
    )

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Marcar merma del lote Salmón fresco',
      }),
    )
    const dialogo = screen.getByRole('dialog', {
      name: 'Marcar merma: Salmón fresco',
    })
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Marcar merma' }),
    )
    await waitFor(() => expect(marcarLoteMerma).toHaveBeenCalled())

    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.mouseDown(dialogo.parentElement as HTMLElement)

    expect(dialogo).toBeInTheDocument()
    for (const boton of within(dialogo).getAllByRole('button', {
      name: 'Cancelar',
    })) {
      expect(boton).toBeDisabled()
    }

    await act(async () => {
      resolver({ ...salmon, estado: 'merma' })
    })
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', {
          name: 'Marcar merma: Salmón fresco',
        }),
      ).not.toBeInTheDocument(),
    )
  })

  it('el gerente no ve acciones de escritura', async () => {
    renderizar('gerente')
    await esperarLotes()

    expect(
      screen.queryByRole('button', { name: 'Agregar lote' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Editar lote/ }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Marcar merma/ }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Eliminar lote/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('Salmón fresco')).toBeInTheDocument()
  })

  it('un lote en merma no ofrece editar, merma ni eliminar', async () => {
    renderizar()
    await esperarLotes()

    const card = screen.getByText('Queso añejo').closest('li') as HTMLElement
    expect(within(card).queryByRole('button')).not.toBeInTheDocument()
  })

  it('advierte una caducidad pasada sin bloquear el guardado', async () => {
    renderizar()
    await esperarLotes()
    vi.mocked(crearLote).mockResolvedValue(salmon)

    const dialogo = abrirFormularioNuevo()
    llenarFormulario(dialogo, { caducidad: '2020-01-01' })

    expect(
      within(dialogo).getByText(/Este lote está vencido/),
    ).toBeInTheDocument()
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar lote' }),
    )

    await waitFor(() =>
      expect(crearLote).toHaveBeenCalledWith(
        expect.objectContaining({ caducidad: '2020-01-01' }),
      ),
    )
  })

  it('renderiza las opciones de estado desde el mapa compartido', async () => {
    const original = ETIQUETA_ESTADO_LOTE.en_riesgo
    ETIQUETA_ESTADO_LOTE.en_riesgo = 'Riesgo de prueba'
    try {
      renderizar()
      await esperarLotes()

      expect(
        screen.getByRole('option', { name: 'Riesgo de prueba' }),
      ).toBeInTheDocument()
    } finally {
      ETIQUETA_ESTADO_LOTE.en_riesgo = original
    }
  })

  it('edita un lote existente aunque no haya cámaras cargadas', async () => {
    const onCambio = vi.fn()
    render(<Inventario rol="dueno" camaras={[]} onCambio={onCambio} />)
    await esperarLotes()
    vi.mocked(actualizarLote).mockResolvedValue(salmon)

    fireEvent.click(
      screen.getByRole('button', { name: 'Editar lote Salmón fresco' }),
    )
    const dialogo = screen.getByRole('dialog', {
      name: 'Editar Salmón fresco',
    })
    expect(
      within(dialogo).getByRole('option', { name: 'Cámara 1' }),
    ).toBeInTheDocument()

    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar lote' }),
    )

    await waitFor(() =>
      expect(actualizarLote).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ camara_id: 1 }),
      ),
    )
    expect(within(dialogo).queryByText('Selecciona una cámara.')).toBeNull()
  })

  it('no sugiere crear una cámara cuando la carga de cámaras falló', async () => {
    vi.mocked(obtenerLotes).mockResolvedValue([])
    render(
      <Inventario
        rol="dueno"
        camaras={[]}
        camarasCargando={false}
        errorCamaras="No se pudieron cargar las cámaras"
      />,
    )

    expect(
      await screen.findByText('No hay lotes registrados.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('No se pudieron cargar las cámaras.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText(
        'Primero agrega una cámara para registrar inventario.',
      ),
    ).not.toBeInTheDocument()
  })

  it('recarga al cambiar versionLotes y quita acciones de una merma', async () => {
    vi.mocked(obtenerLotes)
      .mockResolvedValueOnce([salmon])
      .mockResolvedValueOnce([
        { ...salmon, estado: 'merma', merma_en: '2026-11-16T19:00:00.000Z' },
      ])
    const onCambio = vi.fn()
    const { rerender } = render(
      <Inventario
        rol="dueno"
        camaras={camaras}
        versionLotes={0}
        onCambio={onCambio}
      />,
    )
    await screen.findByText('Salmón fresco')
    expect(
      screen.getByRole('button', { name: 'Editar lote Salmón fresco' }),
    ).toBeInTheDocument()

    rerender(
      <Inventario
        rol="dueno"
        camaras={camaras}
        versionLotes={1}
        onCambio={onCambio}
      />,
    )

    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'Editar lote Salmón fresco' }),
      ).not.toBeInTheDocument(),
    )
    expect(
      screen.queryByRole('button', { name: 'Eliminar lote Salmón fresco' }),
    ).not.toBeInTheDocument()
    expect(obtenerLotes).toHaveBeenCalledTimes(2)
  })

  it('un re-render con las mismas cámaras no vuelve a pedir lotes', async () => {
    const onCambio = vi.fn()
    const { rerender } = render(
      <Inventario
        rol="dueno"
        camaras={camaras}
        versionLotes={0}
        onCambio={onCambio}
      />,
    )
    await esperarLotes()
    const llamadas = vi.mocked(obtenerLotes).mock.calls.length

    rerender(
      <Inventario
        rol="dueno"
        camaras={camaras.map((camara) => ({ ...camara }))}
        versionLotes={0}
        onCambio={onCambio}
      />,
    )

    expect(obtenerLotes).toHaveBeenCalledTimes(llamadas)
  })

  it('no cierra el formulario ni duplica el estado busy mientras guarda', async () => {
    renderizar()
    await esperarLotes()
    let resolver!: (valor: Lote | null) => void
    vi.mocked(crearLote).mockReturnValue(
      new Promise<Lote | null>((resolve) => {
        resolver = resolve
      }),
    )

    const dialogo = abrirFormularioNuevo()
    llenarFormulario(dialogo)
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar lote' }),
    )
    await waitFor(() => expect(crearLote).toHaveBeenCalled())

    expect(
      within(dialogo).getByRole('button', { name: 'Cerrar formulario' }),
    ).toBeDisabled()
    expect(
      within(dialogo).getByRole('button', { name: 'Guardando…' }),
    ).toHaveAttribute('aria-busy', 'true')

    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.mouseDown(dialogo.parentElement as HTMLElement)
    expect(dialogo).toBeInTheDocument()

    await act(async () => {
      resolver(salmon)
    })
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', { name: 'Nuevo lote' }),
      ).not.toBeInTheDocument(),
    )
    expect(crearLote).toHaveBeenCalledTimes(1)
  })

  it('usa centavos en el total del encabezado', async () => {
    vi.mocked(obtenerLotes).mockResolvedValue([
      { ...salmon, id: 10, producto: 'Lote A', costo_total_mxn: 10.4 },
      { ...leche, id: 11, producto: 'Lote B', costo_total_mxn: 10.4 },
    ])
    renderizar()

    expect(await screen.findByText('Lote A')).toBeInTheDocument()
    expect(screen.getByText(/\$20\.80/)).toBeInTheDocument()
  })

  it('muestra la carga de cámaras sin sugerir crearlas', async () => {
    vi.mocked(obtenerLotes).mockResolvedValue([])
    render(
      <Inventario
        rol="dueno"
        camaras={[]}
        camarasCargando
        errorCamaras={null}
      />,
    )

    expect(
      await screen.findByText('No hay lotes registrados.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Cargando cámaras…')).toBeInTheDocument()
    expect(
      screen.queryByText(
        'Primero agrega una cámara para registrar inventario.',
      ),
    ).not.toBeInTheDocument()
  })
})
