import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  actualizarCamara,
  actualizarSensor,
  crearCamara,
  crearSensor,
  eliminarCamara,
  eliminarSensor,
  ErrorApi,
  listarSensores,
  obtenerCamaras,
  rotarTokenSensor,
} from '../api/client'
import type { Camara, Sensor } from '../types'
import { Configuracion } from './Configuracion'

vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>()
  return {
    ...original,
    obtenerCamaras: vi.fn(),
    listarSensores: vi.fn(),
    crearCamara: vi.fn(),
    actualizarCamara: vi.fn(),
    eliminarCamara: vi.fn(),
    crearSensor: vi.fn(),
    rotarTokenSensor: vi.fn(),
    actualizarSensor: vi.fn(),
    eliminarSensor: vi.fn(),
  }
})

const camara: Camara = {
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
}

const sensor: Sensor = {
  id: 'S-1234abcd',
  camara_id: 1,
  camara_nombre: 'Pescados y mariscos',
  activo: true,
  ultima_lectura: '2026-11-16T10:00:00.000Z',
}

const escribirPortapapeles = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(obtenerCamaras).mockResolvedValue([camara])
  vi.mocked(listarSensores).mockResolvedValue([sensor])
  escribirPortapapeles.mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: escribirPortapapeles },
    configurable: true,
  })
})

function renderizar(onCerrar = vi.fn(), onCambio = vi.fn()) {
  render(
    <Configuracion
      abierto
      onCerrar={onCerrar}
      onCambio={onCambio}
      formularioCamaraInicial={false}
    />,
  )
  return { onCerrar, onCambio }
}

async function esperarCamaras() {
  await screen.findByRole('button', {
    name: 'Eliminar cámara Pescados y mariscos',
  })
}

function llenarFormulario(
  dialogo: HTMLElement,
  valores: {
    nombre?: string
    minimo?: string
    maximo?: string
    riesgo?: string
    merma?: string
  } = {},
) {
  const {
    nombre = 'Congelador',
    minimo = '-18',
    maximo = '-15',
    riesgo = '10',
    merma = '60',
  } = valores

  fireEvent.change(within(dialogo).getByLabelText('Nombre de la cámara'), {
    target: { value: nombre },
  })
  fireEvent.change(within(dialogo).getByLabelText('Rango mínimo (°C)'), {
    target: { value: minimo },
  })
  fireEvent.change(within(dialogo).getByLabelText('Rango máximo (°C)'), {
    target: { value: maximo },
  })
  fireEvent.change(within(dialogo).getByLabelText('Minutos para riesgo'), {
    target: { value: riesgo },
  })
  fireEvent.change(within(dialogo).getByLabelText('Minutos para merma'), {
    target: { value: merma },
  })
}

describe('Configuracion', () => {
  it('abre como diálogo modal con la pestaña de cámaras y cierra con el botón', async () => {
    const { onCerrar } = renderizar()
    await esperarCamaras()

    expect(
      screen.getByRole('dialog', { name: 'Configuración' }),
    ).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByRole('tab', { name: 'Cámaras' })).toHaveAttribute(
      'aria-selected',
      'true',
    )

    fireEvent.click(
      screen.getByRole('button', { name: 'Cerrar configuración' }),
    )

    expect(onCerrar).toHaveBeenCalledTimes(1)
  })

  it('cierra con Escape', async () => {
    const { onCerrar } = renderizar()
    await esperarCamaras()

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(onCerrar).toHaveBeenCalledTimes(1)
  })

  it('cambia a la pestaña de sensores y muestra los grupos por cámara', async () => {
    renderizar()
    await esperarCamaras()

    fireEvent.click(screen.getByRole('tab', { name: 'Sensores' }))

    expect(screen.getByRole('tab', { name: 'Sensores' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(
      await screen.findByRole('button', {
        name: 'Agregar sensor a Pescados y mariscos',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('S-1234abcd')).toBeInTheDocument()
    expect(screen.getByText('Activo')).toBeInTheDocument()
  })

  it('crea una cámara con los números del formulario y refresca la lista', async () => {
    const { onCambio } = renderizar()
    await esperarCamaras()
    vi.mocked(crearCamara).mockResolvedValue({
      ...camara,
      id: 9,
      nombre: 'Congelador',
    })

    fireEvent.click(screen.getByRole('button', { name: 'Agregar cámara' }))
    const dialogo = screen.getByRole('dialog', { name: 'Nueva cámara' })
    llenarFormulario(dialogo, { nombre: '  Congelador  ' })
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar cámara' }),
    )

    await waitFor(() =>
      expect(crearCamara).toHaveBeenCalledWith({
        nombre: 'Congelador',
        rango_min_c: -18,
        rango_max_c: -15,
        min_para_riesgo: 10,
        min_para_merma: 60,
      }),
    )
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', { name: 'Nueva cámara' }),
      ).not.toBeInTheDocument(),
    )
    expect(onCambio).toHaveBeenCalledTimes(1)
    expect(obtenerCamaras).toHaveBeenCalledTimes(2)
  })

  it('valida nombre, rango y minutos antes de llamar a la API', async () => {
    renderizar()
    await esperarCamaras()

    fireEvent.click(screen.getByRole('button', { name: 'Agregar cámara' }))
    const dialogo = screen.getByRole('dialog', { name: 'Nueva cámara' })
    llenarFormulario(dialogo, {
      nombre: 'X',
      minimo: '5',
      maximo: '2',
      riesgo: '0',
      merma: '0',
    })
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar cámara' }),
    )

    expect(
      screen.getByText('Escribe un nombre de 2 a 120 caracteres.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('El mínimo debe ser menor que el máximo.'),
    ).toBeInTheDocument()
    expect(
      screen.getAllByText('Escribe un número entero de minutos, mínimo 1.'),
    ).toHaveLength(2)
    expect(crearCamara).not.toHaveBeenCalled()
  })

  it('muestra un mensaje claro ante un 422 del backend', async () => {
    renderizar()
    await esperarCamaras()
    vi.mocked(crearCamara).mockRejectedValue(
      new ErrorApi('La API respondió 422 Unprocessable Entity', 422),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Agregar cámara' }))
    const dialogo = screen.getByRole('dialog', { name: 'Nueva cámara' })
    llenarFormulario(dialogo)
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar cámara' }),
    )

    expect(
      await screen.findByText(
        'Los datos no son válidos. Revisa el nombre, el rango y los minutos.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('dialog', { name: 'Nueva cámara' }),
    ).toBeInTheDocument()
  })

  it('edita una cámara con PATCH y cierra el formulario', async () => {
    renderizar()
    await esperarCamaras()
    vi.mocked(actualizarCamara).mockResolvedValue({
      ...camara,
      nombre: 'Pescados frescos',
    })

    fireEvent.click(
      screen.getByRole('button', { name: 'Editar cámara Pescados y mariscos' }),
    )
    const dialogo = screen.getByRole('dialog', {
      name: 'Editar Pescados y mariscos',
    })
    fireEvent.change(within(dialogo).getByLabelText('Nombre de la cámara'), {
      target: { value: 'Pescados frescos' },
    })
    fireEvent.click(
      within(dialogo).getByRole('button', { name: 'Guardar cámara' }),
    )

    await waitFor(() =>
      expect(actualizarCamara).toHaveBeenCalledWith(1, {
        nombre: 'Pescados frescos',
        rango_min_c: 0,
        rango_max_c: 2,
        min_para_riesgo: 10,
        min_para_merma: 60,
      }),
    )
  })

  it('no borra una cámara con datos y muestra el 409 del backend', async () => {
    renderizar()
    await esperarCamaras()
    const detalle =
      'La cámara tiene datos asociados; desactívala o elimina primero sus sensores.'
    vi.mocked(eliminarCamara).mockRejectedValue(
      new ErrorApi(detalle, 409, null, detalle),
    )

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Eliminar cámara Pescados y mariscos',
      }),
    )
    fireEvent.click(
      within(
        screen.getByRole('dialog', { name: 'Eliminar Pescados y mariscos' }),
      ).getByRole('button', { name: 'Eliminar cámara' }),
    )

    expect(await screen.findByText(detalle)).toBeInTheDocument()
    expect(
      screen.getByRole('button', {
        name: 'Eliminar cámara Pescados y mariscos',
      }),
    ).toBeInTheDocument()
    expect(eliminarCamara).toHaveBeenCalledWith(1)
  })

  it('crea un sensor, muestra el token una vez y permite copiarlo', async () => {
    renderizar()
    await esperarCamaras()
    vi.mocked(crearSensor).mockResolvedValue({
      sensor: {
        id: 'S-nuevo01',
        camara_id: 1,
        camara_nombre: '',
        activo: true,
        ultima_lectura: null,
      },
      token: 'tok-nuevo-en-claro',
    })

    fireEvent.click(screen.getByRole('tab', { name: 'Sensores' }))
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Agregar sensor a Pescados y mariscos',
      }),
    )

    const dialogo = await screen.findByRole('dialog', {
      name: 'Sensor creado',
    })
    expect(within(dialogo).getByLabelText('Token del sensor')).toHaveValue(
      'tok-nuevo-en-claro',
    )
    expect(
      within(dialogo).getByText('Guárdalo ahora; no se volverá a mostrar.'),
    ).toBeInTheDocument()

    fireEvent.click(within(dialogo).getByRole('button', { name: 'Copiar' }))

    await waitFor(() =>
      expect(escribirPortapapeles).toHaveBeenCalledWith('tok-nuevo-en-claro'),
    )
    expect(within(dialogo).getByText('Token copiado.')).toBeInTheDocument()
  })

  it('al cerrar el token lo limpia del estado y de la vista', async () => {
    renderizar()
    await esperarCamaras()
    vi.mocked(crearSensor).mockResolvedValue({
      sensor: {
        id: 'S-nuevo01',
        camara_id: 1,
        camara_nombre: 'Pescados y mariscos',
        activo: true,
        ultima_lectura: null,
      },
      token: 'tok-efimero',
    })

    fireEvent.click(screen.getByRole('tab', { name: 'Sensores' }))
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Agregar sensor a Pescados y mariscos',
      }),
    )
    const dialogo = await screen.findByRole('dialog', {
      name: 'Sensor creado',
    })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar' }))

    expect(
      screen.queryByRole('dialog', { name: 'Sensor creado' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('tok-efimero')).not.toBeInTheDocument()
    expect(screen.queryByText('tok-efimero')).not.toBeInTheDocument()
  })

  it('rota el token y muestra el valor nuevo', async () => {
    renderizar()
    await esperarCamaras()
    vi.mocked(rotarTokenSensor).mockResolvedValue({
      sensor: {
        id: 'S-1234abcd',
        camara_id: 1,
        camara_nombre: '',
        activo: true,
        ultima_lectura: null,
      },
      token: 'tok-rotado',
    })

    fireEvent.click(screen.getByRole('tab', { name: 'Sensores' }))
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Rotar token del sensor S-1234abcd',
      }),
    )

    const dialogo = await screen.findByRole('dialog', {
      name: 'Token rotado',
    })
    expect(within(dialogo).getByLabelText('Token del sensor')).toHaveValue(
      'tok-rotado',
    )
    expect(rotarTokenSensor).toHaveBeenCalledWith('S-1234abcd')
  })

  it('activa y desactiva un sensor con PATCH', async () => {
    renderizar()
    await esperarCamaras()
    vi.mocked(actualizarSensor).mockResolvedValue({
      id: 'S-1234abcd',
      camara_id: 1,
      camara_nombre: 'Pescados y mariscos',
      activo: false,
      ultima_lectura: sensor.ultima_lectura,
    })

    fireEvent.click(screen.getByRole('tab', { name: 'Sensores' }))
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Desactivar sensor S-1234abcd',
      }),
    )

    await waitFor(() =>
      expect(actualizarSensor).toHaveBeenCalledWith('S-1234abcd', {
        activo: false,
      }),
    )
    expect(await screen.findByText('Inactivo')).toBeInTheDocument()
  })

  it('no borra un sensor con lecturas y muestra el 409', async () => {
    renderizar()
    await esperarCamaras()
    const detalle =
      'El sensor tiene lecturas asociadas; desactívalo en lugar de eliminarlo.'
    vi.mocked(eliminarSensor).mockRejectedValue(
      new ErrorApi(detalle, 409, null, detalle),
    )

    fireEvent.click(screen.getByRole('tab', { name: 'Sensores' }))
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Eliminar sensor S-1234abcd',
      }),
    )
    fireEvent.click(
      within(
        screen.getByRole('dialog', { name: 'Eliminar sensor S-1234abcd' }),
      ).getByRole('button', { name: 'Eliminar sensor' }),
    )

    expect(await screen.findByText(detalle)).toBeInTheDocument()
    expect(screen.getByText('S-1234abcd')).toBeInTheDocument()
    expect(eliminarSensor).toHaveBeenCalledWith('S-1234abcd')
  })
})
