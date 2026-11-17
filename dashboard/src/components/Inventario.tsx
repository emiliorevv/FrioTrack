import { memo, useEffect, useMemo, useState } from 'react'
import {
  actualizarLote,
  crearLote,
  eliminarLote,
  marcarLoteMerma,
  obtenerLotes,
} from '../api/client'
import { puedeEditarInventario } from '../auth/roles'
import { mensajeDeError } from '../lib/erroresApi'
import {
  ETIQUETA_ESTADO_LOTE,
  fechaVencida,
  formatearCantidadLote,
  formatearFecha,
  formatearMxnConCentavos,
} from '../lib/format'
import { normalizarTexto } from '../lib/texto'
import type { Camara, EstadoLote, Lote, LoteCreacion } from '../types'
import { Dialogo } from './Dialogo'
import { DialogoConfirmacion } from './DialogoConfirmacion'
import { FormularioLote } from './FormularioLote'
import { TiempoRelativo } from './TiempoRelativo'

type FormularioAbierto =
  { modo: 'crear' } | { modo: 'editar'; lote: Lote } | null

interface Confirmacion {
  tipo: 'merma' | 'eliminar'
  lote: Lote
}

interface InventarioProps {
  rol: string
  camaras: Camara[]
  /** Se incrementa con SSE `lote_actualizado` y con el polling del dashboard. */
  versionLotes?: number
  camarasCargando?: boolean
  errorCamaras?: string | null
  /** Refresca cámaras/KPIs del dashboard después de una mutación. */
  onCambio?: () => void
}

interface LoteVista extends Lote {
  productoNormalizado: string
  vencido: boolean
}

type FiltroEstado = 'todos' | EstadoLote

function prepararLote(lote: Lote): LoteVista {
  return {
    ...lote,
    productoNormalizado: normalizarTexto(lote.producto),
    vencido: fechaVencida(lote.caducidad),
  }
}

function InventarioBase({
  rol,
  camaras,
  versionLotes = 0,
  camarasCargando = false,
  errorCamaras = null,
  onCambio,
}: InventarioProps) {
  const [lotes, setLotes] = useState<LoteVista[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const [busqueda, setBusqueda] = useState('')
  const [camaraFiltro, setCamaraFiltro] = useState('todas')
  const [estadoFiltro, setEstadoFiltro] = useState<FiltroEstado>('todos')
  const [formulario, setFormulario] = useState<FormularioAbierto>(null)
  const [formularioVersion, setFormularioVersion] = useState(0)
  const [guardando, setGuardando] = useState(false)
  const [confirmacion, setConfirmacion] = useState<Confirmacion | null>(null)
  const [procesando, setProcesando] = useState(false)
  const [errorConfirmacion, setErrorConfirmacion] = useState<string | null>(
    null,
  )

  const puedeEditar = puedeEditarInventario(rol)
  const nombresCamara = useMemo(
    () => new Map(camaras.map((camara) => [camara.id, camara.nombre])),
    [camaras],
  )

  useEffect(() => {
    const controlador = new AbortController()
    void obtenerLotes({}, controlador.signal)
      .then((datos) => {
        if (!controlador.signal.aborted) {
          setLotes(datos.map(prepararLote))
        }
      })
      .catch((fallo: unknown) => {
        if (!controlador.signal.aborted) {
          setError(mensajeDeError(fallo, 'lote'))
        }
      })
      .finally(() => {
        if (!controlador.signal.aborted) {
          setCargando(false)
        }
      })
    return () => {
      controlador.abort()
    }
  }, [version, versionLotes])

  function recargar() {
    setError(null)
    setVersion((actual) => actual + 1)
  }

  function reintentar() {
    setCargando(true)
    recargar()
  }

  const consulta = normalizarTexto(busqueda.trim())
  const lotesFiltrados = useMemo(
    () =>
      lotes.filter((lote) => {
        const coincideProducto = lote.productoNormalizado.includes(consulta)
        const coincideCamara =
          camaraFiltro === 'todas' || String(lote.camara_id) === camaraFiltro
        const coincideEstado =
          estadoFiltro === 'todos' || lote.estado === estadoFiltro
        return coincideProducto && coincideCamara && coincideEstado
      }),
    [lotes, consulta, camaraFiltro, estadoFiltro],
  )

  const { totalInventario, lotesActivos } = useMemo(() => {
    const activos = lotes.filter((lote) => lote.estado !== 'merma')
    return {
      totalInventario: activos.reduce(
        (total, lote) => total + lote.costo_total_mxn,
        0,
      ),
      lotesActivos: activos.length,
    }
  }, [lotes])
  const hayFiltros =
    consulta.length > 0 || camaraFiltro !== 'todas' || estadoFiltro !== 'todos'

  function limpiarFiltros() {
    setBusqueda('')
    setCamaraFiltro('todas')
    setEstadoFiltro('todos')
  }

  function abrirFormulario(siguiente: FormularioAbierto) {
    setFormularioVersion((actual) => actual + 1)
    setFormulario(siguiente)
  }

  function cerrarFormulario() {
    if (!guardando) {
      setFormulario(null)
    }
  }

  function abrirCrear() {
    if (puedeEditar && camaras.length > 0) {
      abrirFormulario({ modo: 'crear' })
    }
  }

  function abrirEditar(lote: Lote) {
    if (puedeEditar && lote.estado !== 'merma') {
      abrirFormulario({ modo: 'editar', lote })
    }
  }

  async function guardarLote(datos: LoteCreacion) {
    const formularioActual = formulario
    if (!formularioActual) {
      return
    }

    setGuardando(true)
    try {
      if (formularioActual.modo === 'editar') {
        await actualizarLote(formularioActual.lote.id, datos)
      } else {
        await crearLote(datos)
      }

      // Solo cierra el diálogo que inició esta petición.
      setFormulario((actual) => (actual === formularioActual ? null : actual))
      recargar()
      onCambio?.()
    } finally {
      setGuardando(false)
    }
  }

  function abrirConfirmacion(tipo: Confirmacion['tipo'], lote: Lote) {
    if (!puedeEditar || (tipo === 'eliminar' && lote.estado === 'merma')) {
      return
    }
    setErrorConfirmacion(null)
    setConfirmacion({ tipo, lote })
  }

  async function ejecutarConfirmacion() {
    if (!confirmacion) {
      return
    }
    setProcesando(true)
    setErrorConfirmacion(null)
    try {
      if (confirmacion.tipo === 'merma') {
        await marcarLoteMerma(confirmacion.lote.id)
      } else {
        await eliminarLote(confirmacion.lote.id)
      }
      setConfirmacion(null)
      recargar()
      onCambio?.()
    } catch (fallo) {
      setErrorConfirmacion(mensajeDeError(fallo, 'lote'))
    } finally {
      setProcesando(false)
    }
  }

  return (
    <section className="section" aria-labelledby="inventario-title">
      <div className="section-heading inventario__cabecera">
        <div>
          <h2 id="inventario-title">Inventario</h2>
          <p>
            {lotes.length} {lotes.length === 1 ? 'lote' : 'lotes'} ·{' '}
            {formatearMxnConCentavos(totalInventario)} en {lotesActivos}{' '}
            {lotesActivos === 1 ? 'lote activo' : 'lotes activos'}
          </p>
        </div>
        {puedeEditar && lotes.length > 0 && (
          <button
            type="button"
            className="boton boton--primario"
            onClick={abrirCrear}
            disabled={camaras.length === 0}
          >
            Agregar lote
          </button>
        )}
      </div>

      {lotes.length > 0 && (
        <div className="inventario-filtros">
          <label className="search inventario-buscar">
            <span className="visually-hidden">Buscar producto</span>
            <svg
              className="search__icon"
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input
              type="search"
              value={busqueda}
              onChange={(evento) => setBusqueda(evento.target.value)}
              placeholder="Buscar producto…"
              autoComplete="off"
            />
          </label>

          <label className="inventario-select">
            <span>Cámara</span>
            <select
              value={camaraFiltro}
              onChange={(evento) => setCamaraFiltro(evento.target.value)}
            >
              <option value="todas">Todas las cámaras</option>
              {camaras.map((camara) => (
                <option key={camara.id} value={camara.id}>
                  {camara.nombre}
                </option>
              ))}
            </select>
          </label>

          <label className="inventario-select">
            <span>Estado</span>
            <select
              value={estadoFiltro}
              onChange={(evento) =>
                setEstadoFiltro(evento.target.value as FiltroEstado)
              }
            >
              <option value="todos">Todos</option>
              {(
                Object.entries(ETIQUETA_ESTADO_LOTE) as [EstadoLote, string][]
              ).map(([valor, etiqueta]) => (
                <option key={valor} value={valor}>
                  {etiqueta}
                </option>
              ))}
            </select>
          </label>

          <p className="inventario-conteo" role="status">
            {lotesFiltrados.length} de {lotes.length} lotes
          </p>
        </div>
      )}

      {error && (
        <div className="config-alerta" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="boton boton--secundario boton--sm"
            onClick={reintentar}
          >
            Reintentar
          </button>
        </div>
      )}

      {cargando && lotes.length === 0 ? (
        <p className="empty-state" role="status">
          Cargando inventario…
        </p>
      ) : lotes.length === 0 ? (
        error ? null : (
          <div className="config__vacio inventario-vacio">
            <p>No hay lotes registrados.</p>
            {puedeEditar && camaras.length > 0 && (
              <button
                type="button"
                className="boton boton--primario"
                onClick={abrirCrear}
              >
                Agregar lote
              </button>
            )}
            {puedeEditar && camaras.length === 0 && (
              <p>
                {camarasCargando
                  ? 'Cargando cámaras…'
                  : errorCamaras
                    ? 'No se pudieron cargar las cámaras.'
                    : 'Primero agrega una cámara para registrar inventario.'}
              </p>
            )}
          </div>
        )
      ) : lotesFiltrados.length === 0 ? (
        <div className="config__vacio inventario-vacio">
          <p>No hay lotes que coincidan con los filtros.</p>
          {hayFiltros && (
            <button
              type="button"
              className="boton boton--secundario"
              onClick={limpiarFiltros}
            >
              Limpiar filtros
            </button>
          )}
        </div>
      ) : (
        <ul className="inventario-grid">
          {lotesFiltrados.map((lote) => {
            const merma = lote.estado === 'merma'
            return (
              <li className="lote-card" key={lote.id}>
                <div className="lote-card__cabecera">
                  <h3 className="lote-card__producto">{lote.producto}</h3>
                  <span className={`lote-estado lote-estado--${lote.estado}`}>
                    {ETIQUETA_ESTADO_LOTE[lote.estado]}
                  </span>
                </div>
                <p className="lote-card__camara">
                  {nombresCamara.get(lote.camara_id) ??
                    `Cámara ${lote.camara_id}`}
                </p>

                <dl className="lote-card__datos">
                  <div>
                    <dt>Cantidad</dt>
                    <dd>
                      {formatearCantidadLote(lote.cantidad)} {lote.unidad}
                    </dd>
                  </div>
                  <div>
                    <dt>Costo</dt>
                    <dd>{formatearMxnConCentavos(lote.costo_total_mxn)}</dd>
                  </div>
                  <div className={lote.vencido ? 'is-warn' : undefined}>
                    <dt>Caducidad</dt>
                    <dd>
                      {formatearFecha(lote.caducidad)}
                      {lote.vencido && (
                        <span className="lote-vencido">Vencido</span>
                      )}
                    </dd>
                  </div>
                  {lote.merma_en && (
                    <div>
                      <dt>Merma</dt>
                      <dd>
                        <TiempoRelativo ts={lote.merma_en} />
                      </dd>
                    </div>
                  )}
                </dl>

                {puedeEditar && !merma && (
                  <div className="lote-card__acciones">
                    <button
                      type="button"
                      className="boton boton--secundario boton--sm"
                      onClick={() => abrirEditar(lote)}
                      aria-label={`Editar lote ${lote.producto}`}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="boton boton--advertencia boton--sm"
                      onClick={() => abrirConfirmacion('merma', lote)}
                      aria-label={`Marcar merma del lote ${lote.producto}`}
                    >
                      Marcar merma
                    </button>
                    <button
                      type="button"
                      className="boton boton--peligro boton--sm"
                      onClick={() => abrirConfirmacion('eliminar', lote)}
                      aria-label={`Eliminar lote ${lote.producto}`}
                    >
                      Eliminar
                    </button>
                  </div>
                )}
                {!puedeEditar && (
                  <p className="lote-card__solo-lectura">Solo lectura</p>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {formulario && (
        <Dialogo
          titulo={
            formulario.modo === 'crear'
              ? 'Nuevo lote'
              : `Editar ${formulario.lote.producto}`
          }
          onCerrar={cerrarFormulario}
          etiquetaCerrar="Cerrar formulario"
          cerrable={!guardando}
        >
          <FormularioLote
            key={formularioVersion}
            lote={formulario.modo === 'editar' ? formulario.lote : undefined}
            camaras={camaras}
            guardando={guardando}
            onGuardar={guardarLote}
            onCancelar={cerrarFormulario}
          />
        </Dialogo>
      )}

      {confirmacion && (
        <DialogoConfirmacion
          titulo={
            confirmacion.tipo === 'merma'
              ? `Marcar merma: ${confirmacion.lote.producto}`
              : `Eliminar lote: ${confirmacion.lote.producto}`
          }
          mensaje={
            confirmacion.tipo === 'merma'
              ? 'El lote se conservará en el historial de merma y dejará de contar como inventario activo.'
              : 'El lote se borrará del inventario. Esta acción no se puede deshacer.'
          }
          etiquetaConfirmar={
            confirmacion.tipo === 'merma' ? 'Marcar merma' : 'Eliminar lote'
          }
          etiquetaOcupado={
            confirmacion.tipo === 'merma' ? 'Marcando…' : 'Eliminando…'
          }
          peligro={confirmacion.tipo === 'eliminar'}
          error={errorConfirmacion}
          ocupado={procesando}
          cerrable={!procesando}
          onCancelar={() => setConfirmacion(null)}
          onConfirmar={() => void ejecutarConfirmacion()}
        />
      )}
    </section>
  )
}

function mismasCamaras(a: Camara[], b: Camara[]): boolean {
  return (
    a.length === b.length &&
    a.every(
      (camara, indice) =>
        camara.id === b[indice].id && camara.nombre === b[indice].nombre,
    )
  )
}

/**
 * Solo se re-renderiza cuando cambia algo visible para Inventario; una lectura
 * SSE que reemplaza el array de cámaras con los mismos ids/nombres no reabre
 * la carga de lotes.
 */
export const Inventario = memo(
  InventarioBase,
  (previas, siguientes) =>
    previas.rol === siguientes.rol &&
    previas.versionLotes === siguientes.versionLotes &&
    previas.camarasCargando === siguientes.camarasCargando &&
    previas.errorCamaras === siguientes.errorCamaras &&
    previas.onCambio === siguientes.onCambio &&
    mismasCamaras(previas.camaras, siguientes.camaras),
)
