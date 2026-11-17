import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react'
import {
  actualizarCamara,
  actualizarSensor,
  crearCamara,
  crearSensor,
  eliminarCamara,
  eliminarSensor,
  listarSensores,
  obtenerCamaras,
  rotarTokenSensor,
} from '../api/client'
import { mensajeDeError } from '../lib/erroresApi'
import { ETIQUETA_ESTADO } from '../lib/format'
import type { Camara, CamaraCreacion, Sensor } from '../types'
import { Dialogo } from './Dialogo'
import { DialogoConfirmacion } from './DialogoConfirmacion'
import { FormularioCamara } from './FormularioCamara'
import { TiempoRelativo } from './TiempoRelativo'

type Pestana = 'camaras' | 'sensores'

type FormularioAbierto =
  { modo: 'crear' } | { modo: 'editar'; camara: Camara } | null

interface TokenVisible {
  sensor: Sensor
  token: string
  origen: 'creado' | 'rotado'
}

interface ConfiguracionProps {
  onCerrar: () => void
  /** Se llama después de crear, editar o borrar una cámara. */
  onCambio?: () => void
  /** Abre directamente el formulario de alta (onboarding). */
  formularioCamaraInicial?: boolean
}

export function Configuracion({
  onCerrar,
  onCambio,
  formularioCamaraInicial = false,
}: ConfiguracionProps) {
  const [pestana, setPestana] = useState<Pestana>('camaras')
  const [camaras, setCamaras] = useState<Camara[]>([])
  const [sensores, setSensores] = useState<Sensor[]>([])
  const [cargandoCamaras, setCargandoCamaras] = useState(true)
  const [cargandoSensores, setCargandoSensores] = useState(true)
  const [errorCamaras, setErrorCamaras] = useState<string | null>(null)
  const [errorSensores, setErrorSensores] = useState<string | null>(null)
  const [errorAccion, setErrorAccion] = useState<string | null>(null)
  const [versionCamaras, setVersionCamaras] = useState(0)
  const [versionSensores, setVersionSensores] = useState(0)
  const [formulario, setFormulario] = useState<FormularioAbierto>(() =>
    formularioCamaraInicial ? { modo: 'crear' } : null,
  )
  const [formularioVersion, setFormularioVersion] = useState(0)
  const [guardandoCamara, setGuardandoCamara] = useState(false)
  const [confirmarCamara, setConfirmarCamara] = useState<Camara | null>(null)
  const [confirmarSensor, setConfirmarSensor] = useState<Sensor | null>(null)
  const [errorConfirmacion, setErrorConfirmacion] = useState<string | null>(
    null,
  )
  const [eliminando, setEliminando] = useState(false)
  const [tokenVisible, setTokenVisible] = useState<TokenVisible | null>(null)
  const [copiado, setCopiado] = useState(false)
  const [errorCopia, setErrorCopia] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState<string | null>(null)

  const baseId = useId()
  const tabsRef = useRef<Record<Pestana, HTMLButtonElement | null>>({
    camaras: null,
    sensores: null,
  })

  useEffect(() => {
    const controlador = new AbortController()
    void obtenerCamaras(controlador.signal)
      .then((datos) => {
        if (!controlador.signal.aborted) {
          setCamaras(datos)
        }
      })
      .catch((error: unknown) => {
        if (!controlador.signal.aborted) {
          setErrorCamaras(mensajeDeError(error, 'camara'))
        }
      })
      .finally(() => {
        if (!controlador.signal.aborted) {
          setCargandoCamaras(false)
        }
      })
    return () => {
      controlador.abort()
    }
  }, [versionCamaras])

  useEffect(() => {
    const controlador = new AbortController()
    void listarSensores(controlador.signal)
      .then((datos) => {
        if (!controlador.signal.aborted) {
          setSensores(datos)
        }
      })
      .catch((error: unknown) => {
        if (!controlador.signal.aborted) {
          setErrorSensores(mensajeDeError(error, 'sensor'))
        }
      })
      .finally(() => {
        if (!controlador.signal.aborted) {
          setCargandoSensores(false)
        }
      })
    return () => {
      controlador.abort()
    }
  }, [versionSensores])

  const grupos = useMemo(() => {
    const porCamara = new Map<
      number,
      {
        camaraId: number
        camara: Camara | null
        nombre: string
        sensores: Sensor[]
      }
    >()

    for (const camara of camaras) {
      porCamara.set(camara.id, {
        camaraId: camara.id,
        camara,
        nombre: camara.nombre,
        sensores: [],
      })
    }

    // Si falló el listado de cámaras, los sensores ya cargados se agrupan por
    // el nombre que trae `GET /sensores` en vez de desaparecer.
    for (const sensor of sensores) {
      const grupo = porCamara.get(sensor.camara_id)
      if (grupo) {
        grupo.sensores.push(sensor)
      } else {
        porCamara.set(sensor.camara_id, {
          camaraId: sensor.camara_id,
          camara: null,
          nombre: sensor.camara_nombre || `Cámara ${sensor.camara_id}`,
          sensores: [sensor],
        })
      }
    }

    return [...porCamara.values()]
  }, [camaras, sensores])

  function recargarCamaras() {
    setErrorCamaras(null)
    setVersionCamaras((version) => version + 1)
  }

  function recargarSensores() {
    setErrorSensores(null)
    setVersionSensores((version) => version + 1)
  }

  function reintentarCamaras() {
    setCargandoCamaras(true)
    recargarCamaras()
  }

  function reintentarSensores() {
    setCargandoSensores(true)
    recargarSensores()
  }

  function cambiarPestana(siguiente: Pestana) {
    setPestana(siguiente)
    setErrorAccion(null)
  }

  function alTeclearPestanas(evento: KeyboardEvent<HTMLDivElement>) {
    if (evento.key !== 'ArrowLeft' && evento.key !== 'ArrowRight') {
      return
    }
    evento.preventDefault()
    const siguiente: Pestana = pestana === 'camaras' ? 'sensores' : 'camaras'
    cambiarPestana(siguiente)
    tabsRef.current[siguiente]?.focus()
  }

  function abrirFormulario(siguiente: FormularioAbierto) {
    setGuardandoCamara(false)
    setFormularioVersion((version) => version + 1)
    setFormulario(siguiente)
  }

  function cerrarFormulario() {
    if (!guardandoCamara) {
      setFormulario(null)
    }
  }

  async function guardarCamara(datos: CamaraCreacion) {
    const formularioActual = formulario
    if (!formularioActual) {
      return
    }

    setGuardandoCamara(true)
    try {
      if (formularioActual.modo === 'editar') {
        await actualizarCamara(formularioActual.camara.id, datos)
      } else {
        await crearCamara(datos)
      }

      // Solo cierra el formulario que inició esta petición.
      setFormulario((actual) => (actual === formularioActual ? null : actual))
      recargarCamaras()
      recargarSensores()
      onCambio?.()
    } finally {
      setGuardandoCamara(false)
    }
  }

  function pedirEliminarCamara(camara: Camara) {
    setErrorConfirmacion(null)
    setConfirmarCamara(camara)
  }

  async function borrarCamara() {
    if (!confirmarCamara) {
      return
    }
    setEliminando(true)
    setErrorConfirmacion(null)
    try {
      await eliminarCamara(confirmarCamara.id)
      setConfirmarCamara(null)
      recargarCamaras()
      recargarSensores()
      onCambio?.()
    } catch (error) {
      setErrorConfirmacion(mensajeDeError(error, 'camara'))
    } finally {
      setEliminando(false)
    }
  }

  async function pedirCrearSensor(camara: Camara) {
    const clave = `crear-sensor-${camara.id}`
    setOcupado(clave)
    setErrorAccion(null)
    try {
      const resultado = await crearSensor(camara.id)
      setTokenVisible({
        sensor: {
          ...resultado.sensor,
          camara_nombre: resultado.sensor.camara_nombre || camara.nombre,
        },
        token: resultado.token,
        origen: 'creado',
      })
      setCopiado(false)
      setErrorCopia(null)
      recargarSensores()
    } catch (error) {
      setErrorAccion(mensajeDeError(error, 'sensor'))
    } finally {
      setOcupado(null)
    }
  }

  async function rotarToken(sensor: Sensor) {
    const clave = `rotar-${sensor.id}`
    setOcupado(clave)
    setErrorAccion(null)
    try {
      const resultado = await rotarTokenSensor(sensor.id)
      setTokenVisible({
        sensor: {
          ...sensor,
          ...resultado.sensor,
          camara_nombre: resultado.sensor.camara_nombre || sensor.camara_nombre,
          ultima_lectura: sensor.ultima_lectura,
        },
        token: resultado.token,
        origen: 'rotado',
      })
      setCopiado(false)
      setErrorCopia(null)
    } catch (error) {
      setErrorAccion(mensajeDeError(error, 'sensor'))
    } finally {
      setOcupado(null)
    }
  }

  async function alternarSensor(sensor: Sensor) {
    const clave = `activar-${sensor.id}`
    setOcupado(clave)
    setErrorAccion(null)
    try {
      const actualizado = await actualizarSensor(sensor.id, {
        activo: !sensor.activo,
      })
      setSensores((previos) =>
        previos.map((actual) =>
          actual.id === sensor.id
            ? {
                ...actual,
                activo: actualizado.activo,
              }
            : actual,
        ),
      )
    } catch (error) {
      setErrorAccion(mensajeDeError(error, 'sensor'))
    } finally {
      setOcupado(null)
    }
  }

  function pedirEliminarSensor(sensor: Sensor) {
    setErrorConfirmacion(null)
    setConfirmarSensor(sensor)
  }

  async function borrarSensor() {
    if (!confirmarSensor) {
      return
    }
    setEliminando(true)
    setErrorConfirmacion(null)
    try {
      await eliminarSensor(confirmarSensor.id)
      setConfirmarSensor(null)
      recargarSensores()
    } catch (error) {
      setErrorConfirmacion(mensajeDeError(error, 'sensor'))
    } finally {
      setEliminando(false)
    }
  }

  async function copiarToken() {
    if (!tokenVisible) {
      return
    }
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error('Clipboard no disponible')
      }
      await navigator.clipboard.writeText(tokenVisible.token)
      setCopiado(true)
      setErrorCopia(null)
    } catch {
      setErrorCopia(
        'No se pudo copiar automáticamente. Selecciona el token y cópialo a mano.',
      )
    }
  }

  return (
    <>
      <Dialogo
        titulo="Configuración"
        onCerrar={onCerrar}
        etiquetaCerrar="Cerrar configuración"
        className="config"
      >
        <div
          className="config__tabs"
          role="tablist"
          aria-label="Cámaras y sensores"
          onKeyDown={alTeclearPestanas}
        >
          <button
            type="button"
            role="tab"
            id={`${baseId}-tab-camaras`}
            aria-selected={pestana === 'camaras'}
            aria-controls={`${baseId}-panel-camaras`}
            className="config__tab"
            ref={(nodo) => {
              tabsRef.current.camaras = nodo
            }}
            onClick={() => cambiarPestana('camaras')}
          >
            Cámaras
          </button>
          <button
            type="button"
            role="tab"
            id={`${baseId}-tab-sensores`}
            aria-selected={pestana === 'sensores'}
            aria-controls={`${baseId}-panel-sensores`}
            className="config__tab"
            ref={(nodo) => {
              tabsRef.current.sensores = nodo
            }}
            onClick={() => cambiarPestana('sensores')}
          >
            Sensores
          </button>
        </div>

        {errorAccion && (
          <p className="config-alerta" role="alert">
            {errorAccion}
          </p>
        )}

        <div
          id={`${baseId}-panel-camaras`}
          role="tabpanel"
          aria-labelledby={`${baseId}-tab-camaras`}
          hidden={pestana !== 'camaras'}
          className="config__panel"
        >
          <div className="config__barra">
            <div>
              <h3 className="config__subtitulo">Tus cámaras</h3>
              <p className="config__nota">
                Rangos y tiempos que usa FríoTrack para avisarte.
              </p>
            </div>
            <button
              type="button"
              className="boton boton--primario"
              onClick={() => abrirFormulario({ modo: 'crear' })}
            >
              Agregar cámara
            </button>
          </div>

          {errorCamaras && (
            <div className="config-alerta" role="alert">
              <p>{errorCamaras}</p>
              <button
                type="button"
                className="boton boton--secundario boton--sm"
                onClick={reintentarCamaras}
              >
                Reintentar
              </button>
            </div>
          )}

          {cargandoCamaras && camaras.length === 0 ? (
            <p className="config__vacio" role="status">
              Cargando cámaras…
            </p>
          ) : camaras.length === 0 ? (
            errorCamaras ? null : (
              <div className="config__vacio">
                <p>Todavía no hay cámaras registradas.</p>
                <button
                  type="button"
                  className="boton boton--primario"
                  onClick={() => abrirFormulario({ modo: 'crear' })}
                >
                  Agregar cámara
                </button>
              </div>
            )
          ) : (
            <ul className="config-lista">
              {camaras.map((camara) => (
                <li className="config-camara" key={camara.id}>
                  <div className="config-camara__info">
                    <p className="config-camara__nombre">{camara.nombre}</p>
                    <p className="config-camara__datos">
                      {camara.rango_min_c} °C a {camara.rango_max_c} °C · riesgo
                      a los {camara.min_para_riesgo} min · merma a los{' '}
                      {camara.min_para_merma} min
                    </p>
                  </div>
                  <span
                    className={`status status--${camara.estado}`}
                    title={`Estado: ${camara.estado}`}
                  >
                    <span className="status__dot" aria-hidden="true" />
                    {ETIQUETA_ESTADO[camara.estado]}
                  </span>
                  <div className="config-camara__acciones">
                    <button
                      type="button"
                      className="boton boton--secundario boton--sm"
                      onClick={() =>
                        abrirFormulario({ modo: 'editar', camara })
                      }
                      aria-label={`Editar cámara ${camara.nombre}`}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="boton boton--peligro boton--sm"
                      onClick={() => pedirEliminarCamara(camara)}
                      aria-label={`Eliminar cámara ${camara.nombre}`}
                    >
                      Eliminar
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div
          id={`${baseId}-panel-sensores`}
          role="tabpanel"
          aria-labelledby={`${baseId}-tab-sensores`}
          hidden={pestana !== 'sensores'}
          className="config__panel"
        >
          <div className="config__barra">
            <div>
              <h3 className="config__subtitulo">Sensores</h3>
              <p className="config__nota">
                Cada cámara necesita un sensor con su token para enviar
                lecturas.
              </p>
            </div>
          </div>

          {errorSensores && (
            <div className="config-alerta" role="alert">
              <p>{errorSensores}</p>
              <button
                type="button"
                className="boton boton--secundario boton--sm"
                onClick={reintentarSensores}
              >
                Reintentar
              </button>
            </div>
          )}

          {errorCamaras && (
            <div className="config-alerta" role="alert">
              <p>{errorCamaras}</p>
              <button
                type="button"
                className="boton boton--secundario boton--sm"
                onClick={reintentarCamaras}
              >
                Reintentar
              </button>
            </div>
          )}

          {camaras.length === 0 && !cargandoCamaras && !errorCamaras ? (
            <div className="config__vacio">
              <p>Primero agrega una cámara para conectar un sensor.</p>
              <button
                type="button"
                className="boton boton--primario"
                onClick={() => {
                  cambiarPestana('camaras')
                  abrirFormulario({ modo: 'crear' })
                }}
              >
                Agregar cámara
              </button>
            </div>
          ) : cargandoSensores && sensores.length === 0 ? (
            <p className="config__vacio" role="status">
              Cargando sensores…
            </p>
          ) : errorSensores && sensores.length === 0 ? null : (
            <div className="sensor-grupos">
              {grupos.map(
                ({ camaraId, camara, nombre, sensores: sensoresCamara }) => (
                  <section
                    className="sensor-grupo"
                    key={camaraId}
                    aria-labelledby={`${baseId}-grupo-${camaraId}`}
                  >
                    <div className="sensor-grupo__cabecera">
                      <h4
                        className="sensor-grupo__titulo"
                        id={`${baseId}-grupo-${camaraId}`}
                      >
                        {nombre}
                      </h4>
                      {camara && (
                        <button
                          type="button"
                          className="boton boton--secundario boton--sm"
                          onClick={() => void pedirCrearSensor(camara)}
                          aria-busy={ocupado === `crear-sensor-${camara.id}`}
                          aria-label={`Agregar sensor a ${camara.nombre}`}
                          disabled={ocupado !== null}
                        >
                          {ocupado === `crear-sensor-${camara.id}`
                            ? 'Creando…'
                            : 'Agregar sensor'}
                        </button>
                      )}
                    </div>

                    {sensoresCamara.length === 0 ? (
                      <p className="sensor-grupo__vacio">
                        Sin sensores conectados.
                      </p>
                    ) : (
                      <ul className="sensor-lista">
                        {sensoresCamara.map((sensor) => (
                          <li className="sensor-fila" key={sensor.id}>
                            <div className="sensor-fila__info">
                              <p className="sensor-fila__id">{sensor.id}</p>
                              <p className="sensor-fila__meta">
                                Última lectura:{' '}
                                {sensor.ultima_lectura ? (
                                  <TiempoRelativo ts={sensor.ultima_lectura} />
                                ) : (
                                  'sin lecturas'
                                )}
                              </p>
                            </div>
                            <span
                              className={`sensor-estado ${
                                sensor.activo
                                  ? 'sensor-estado--activo'
                                  : 'sensor-estado--inactivo'
                              }`}
                            >
                              {sensor.activo ? 'Activo' : 'Inactivo'}
                            </span>
                            <div className="sensor-fila__acciones">
                              <button
                                type="button"
                                className="boton boton--secundario boton--sm"
                                onClick={() => void rotarToken(sensor)}
                                aria-busy={ocupado === `rotar-${sensor.id}`}
                                aria-label={`Rotar token del sensor ${sensor.id}`}
                                disabled={ocupado !== null}
                              >
                                {ocupado === `rotar-${sensor.id}`
                                  ? 'Rotando…'
                                  : 'Rotar token'}
                              </button>
                              <button
                                type="button"
                                className="boton boton--secundario boton--sm"
                                onClick={() => void alternarSensor(sensor)}
                                aria-busy={ocupado === `activar-${sensor.id}`}
                                aria-label={`${
                                  sensor.activo ? 'Desactivar' : 'Activar'
                                } sensor ${sensor.id}`}
                                disabled={ocupado !== null}
                              >
                                {ocupado === `activar-${sensor.id}`
                                  ? 'Guardando…'
                                  : sensor.activo
                                    ? 'Desactivar'
                                    : 'Activar'}
                              </button>
                              <button
                                type="button"
                                className="boton boton--peligro boton--sm"
                                onClick={() => pedirEliminarSensor(sensor)}
                                aria-label={`Eliminar sensor ${sensor.id}`}
                                disabled={ocupado !== null}
                              >
                                Eliminar
                              </button>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                ),
              )}
              {grupos.length === 0 && !errorCamaras && (
                <p className="sensor-grupo__vacio">Sin sensores conectados.</p>
              )}
            </div>
          )}
        </div>
      </Dialogo>

      {formulario && (
        <Dialogo
          titulo={
            formulario.modo === 'crear'
              ? 'Nueva cámara'
              : `Editar ${formulario.camara.nombre}`
          }
          onCerrar={cerrarFormulario}
          etiquetaCerrar="Cerrar formulario"
          cerrable={!guardandoCamara}
        >
          <FormularioCamara
            key={formularioVersion}
            camara={
              formulario.modo === 'editar' ? formulario.camara : undefined
            }
            onGuardar={guardarCamara}
            onCancelar={cerrarFormulario}
          />
        </Dialogo>
      )}

      {confirmarCamara && (
        <DialogoConfirmacion
          titulo={`Eliminar ${confirmarCamara.nombre}`}
          mensaje="La cámara se borrará de forma permanente. Si tiene sensores o lecturas, no se podrá eliminar."
          etiquetaConfirmar="Eliminar cámara"
          error={errorConfirmacion}
          ocupado={eliminando}
          etiquetaOcupado="Eliminando…"
          cerrable={!eliminando}
          onCancelar={() => setConfirmarCamara(null)}
          onConfirmar={() => void borrarCamara()}
        />
      )}

      {confirmarSensor && (
        <DialogoConfirmacion
          titulo={`Eliminar sensor ${confirmarSensor.id}`}
          mensaje="Si el sensor ya envió lecturas, FríoTrack pedirá desactivarlo en lugar de borrarlo."
          etiquetaConfirmar="Eliminar sensor"
          error={errorConfirmacion}
          ocupado={eliminando}
          etiquetaOcupado="Eliminando…"
          cerrable={!eliminando}
          onCancelar={() => setConfirmarSensor(null)}
          onConfirmar={() => void borrarSensor()}
        />
      )}

      {tokenVisible && (
        <Dialogo
          titulo={
            tokenVisible.origen === 'creado' ? 'Sensor creado' : 'Token rotado'
          }
          onCerrar={() => setTokenVisible(null)}
          etiquetaCerrar="Cerrar token"
        >
          <p className="token-aviso">
            Guárdalo ahora; no se volverá a mostrar.
          </p>
          <p className="token-meta">
            {tokenVisible.sensor.id} · {tokenVisible.sensor.camara_nombre}
          </p>
          <div className="token-caja">
            <input
              className="token-texto"
              type="text"
              readOnly
              value={tokenVisible.token}
              aria-label="Token del sensor"
              onFocus={(evento) => evento.currentTarget.select()}
            />
            <button
              type="button"
              className="boton boton--primario"
              onClick={() => void copiarToken()}
            >
              Copiar
            </button>
          </div>
          {copiado && (
            <p className="token-copiado" role="status">
              Token copiado.
            </p>
          )}
          {errorCopia && (
            <p className="config-alerta" role="alert">
              {errorCopia}
            </p>
          )}
          <p className="config__nota">
            Configúralo en el sensor o gateway de esta cámara. El token anterior
            deja de funcionar al rotarlo.
          </p>
          <div className="config-form__acciones">
            <button
              type="button"
              className="boton boton--secundario"
              onClick={() => setTokenVisible(null)}
            >
              Cerrar
            </button>
          </div>
        </Dialogo>
      )}
    </>
  )
}
