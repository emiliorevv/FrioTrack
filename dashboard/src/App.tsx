import { useState } from 'react'
import './App.css'
import { puedeAtenderAlertas } from './auth/roles'
import { AlertasActivas } from './components/AlertasActivas'
import { CameraCard } from './components/CameraCard'
import { FilterBar } from './components/FilterBar'
import { Header } from './components/Header'
import { KpiStrip } from './components/KpiStrip'
import { NotificationToast } from './components/NotificationToast'
import { OnboardingBanner } from './components/OnboardingBanner'
import { SecurityPanel } from './components/SecurityPanel'
import { TiempoRelativo } from './components/TiempoRelativo'
import { useDashboard } from './hooks/useDashboard'
import { useNotificaciones } from './hooks/useNotificaciones'
import { useReloj } from './hooks/useReloj'
import type { FiltroCamaras } from './types'

/** Pasado este tiempo sin datos nuevos, el pie deja de decir "en vivo". */
const UMBRAL_DATOS_VIEJOS_MS = 90_000

function fechaMasReciente(a: Date | null, b: Date | null): Date | null {
  if (!a) {
    return b
  }
  if (!b) {
    return a
  }
  return a.getTime() >= b.getTime() ? a : b
}

function estaVigente(fecha: Date | null, ahora: Date): boolean {
  return (
    fecha !== null &&
    ahora.getTime() - fecha.getTime() <= UMBRAL_DATOS_VIEJOS_MS
  )
}

function normalizar(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
}

interface AppProps {
  usuario: string
  rol: string
  onLogout: () => void
}

function App({ usuario, rol, onLogout }: AppProps) {
  const [filtro, setFiltro] = useState<FiltroCamaras>('todas')
  const [busqueda, setBusqueda] = useState('')
  const { notificacion, cerrar } = useNotificaciones()
  const {
    health,
    camaras,
    kpis,
    alertasSeguridad,
    alertasCargadas,
    errorAlertasSeguridad,
    alertasActivas,
    cargandoAlertas,
    errorAlertas,
    errorAtender,
    limpiarErrorAtender,
    atendiendo,
    atenderAlerta,
    series,
    cargando,
    errorResumen,
    ultimoExitoHttp,
    ultimaActividadSse,
    refrescar,
  } = useDashboard()

  const consulta = normalizar(busqueda.trim())
  const camarasFiltradas = camaras.filter((camara) => {
    const coincideEstado = filtro === 'todas' || camara.estado === filtro
    const coincideBusqueda = normalizar(camara.nombre).includes(consulta)
    return coincideEstado && coincideBusqueda
  })

  const conteos: Record<FiltroCamaras, number> = {
    todas: camaras.length,
    en_rango: camaras.filter((camara) => camara.estado === 'en_rango').length,
    alerta: camaras.filter((camara) => camara.estado === 'alerta').length,
    critica: camaras.filter((camara) => camara.estado === 'critica').length,
  }

  const equiposEnAlerta = conteos.alerta + conteos.critica
  const sinDatos = camaras.length === 0 && kpis === null
  const mostrarBienvenida = camaras.length === 0 && !cargando && !errorResumen
  const actualizadoEn = fechaMasReciente(ultimoExitoHttp, ultimaActividadSse)

  return (
    <div className="app">
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>

      <Header
        actualizadoEn={actualizadoEn}
        escalaTiempo={health?.escala_tiempo}
        usuario={usuario}
        rol={rol}
        onLogout={onLogout}
      />

      <main id="contenido" className="app-main" tabIndex={-1}>
        {errorResumen && sinDatos ? (
          <section className="error-panel" role="alert">
            <h2>No se pudo cargar el dashboard</h2>
            <p>{errorResumen}</p>
            <button
              type="button"
              className="retry-button"
              disabled={cargando}
              aria-busy={cargando}
              onClick={() => void refrescar()}
            >
              {cargando ? 'Reintentando…' : 'Reintentar'}
            </button>
          </section>
        ) : cargando && sinDatos ? (
          <EsqueletoDashboard />
        ) : (
          <>
            {errorResumen && (
              <AvisoResumen
                error={errorResumen}
                ultimoExitoHttp={ultimoExitoHttp}
                ultimaActividadSse={ultimaActividadSse}
                onReintentar={() => void refrescar()}
              />
            )}

            {camaras.length > 0 && <OnboardingBanner />}

            {mostrarBienvenida && <BienvenidaRestaurante />}

            <section className="section" aria-labelledby="resumen-title">
              <div className="section-heading">
                <div>
                  <h2 id="resumen-title">Resumen de hoy</h2>
                  <p>Últimas 24 horas · turno de comida</p>
                  <details className="explicacion">
                    <summary>¿Qué es esto?</summary>
                    <div className="explicacion__cuerpo">
                      <p>
                        El % en rango cubre las últimas 24 horas. Las alertas
                        activas y el valor en riesgo son del momento actual. El
                        tiempo de respuesta es el promedio de las alertas ya
                        atendidas. La merma es de hoy y del mes en curso.
                      </p>
                    </div>
                  </details>
                </div>
              </div>
              {kpis && <KpiStrip kpis={kpis} />}
            </section>

            <AlertasActivas
              alertas={alertasActivas}
              camaras={camaras}
              cargando={cargandoAlertas}
              error={errorAlertas}
              errorAtender={errorAtender}
              atendiendo={atendiendo}
              puedeAtender={puedeAtenderAlertas(rol)}
              onAtender={(id) => void atenderAlerta(id)}
              onLimpiarErrorAtender={limpiarErrorAtender}
            />

            <section className="section" aria-labelledby="camaras-title">
              <div className="section-heading">
                <div>
                  <h2 id="camaras-title">Cámaras</h2>
                  <p>
                    {camaras.length} equipos · {equiposEnAlerta} en alerta
                  </p>
                </div>
              </div>

              {camaras.length > 0 && (
                <FilterBar
                  filtro={filtro}
                  onFiltro={setFiltro}
                  busqueda={busqueda}
                  onBusqueda={setBusqueda}
                  conteos={conteos}
                  visibles={camarasFiltradas.length}
                />
              )}

              {camarasFiltradas.length > 0 ? (
                <div className="camera-grid">
                  {camarasFiltradas.map((camara) => (
                    <CameraCard
                      key={camara.id}
                      camara={camara}
                      serie={series[camara.id] ?? []}
                    />
                  ))}
                </div>
              ) : camaras.length > 0 ? (
                <p className="empty-state">
                  No hay cámaras que coincidan con el filtro.
                </p>
              ) : (
                <p className="empty-state">Aquí aparecerán tus cámaras.</p>
              )}
            </section>

            <SecurityPanel
              alertas={alertasSeguridad}
              cargado={alertasCargadas}
              error={errorAlertasSeguridad}
            />
          </>
        )}
      </main>

      <PieEstado
        ultimoExitoHttp={ultimoExitoHttp}
        ultimaActividadSse={ultimaActividadSse}
        errorResumen={errorResumen}
      />

      {notificacion && (
        <NotificationToast
          key={notificacion.id}
          notificacion={notificacion.datos}
          onCerrar={cerrar}
        />
      )}
    </div>
  )
}

/** Estado vacío de un restaurante recién creado: guía los primeros pasos. */
function BienvenidaRestaurante() {
  return (
    <section className="bienvenida" aria-labelledby="bienvenida-title">
      <p className="bienvenida__eyebrow">Primeros pasos</p>
      <h2 className="bienvenida__title" id="bienvenida-title">
        Tu restaurante está listo
      </h2>
      <p className="bienvenida__text">
        Aún no tienes cámaras. El siguiente paso es agregar la primera y
        conectar su sensor.
      </p>

      <ol className="bienvenida__pasos">
        <li className="bienvenida__paso bienvenida__paso--hecho">
          <span className="bienvenida__numero" aria-hidden="true">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m5 13 4 4L19 7" />
            </svg>
          </span>
          <span className="bienvenida__paso-texto">
            <span className="bienvenida__paso-titulo">Crea tu restaurante</span>
            <span className="bienvenida__paso-estado">Completado</span>
          </span>
        </li>

        <li
          className="bienvenida__paso bienvenida__paso--siguiente"
          aria-current="step"
        >
          <span className="bienvenida__numero" aria-hidden="true">
            2
          </span>
          <span className="bienvenida__paso-texto">
            <span className="bienvenida__paso-titulo">Agrega una cámara</span>
            <span className="bienvenida__paso-estado">Siguiente</span>
          </span>
        </li>

        <li className="bienvenida__paso">
          <span className="bienvenida__numero" aria-hidden="true">
            3
          </span>
          <span className="bienvenida__paso-texto">
            <span className="bienvenida__paso-titulo">Conecta el sensor</span>
            <span className="bienvenida__paso-estado">Después</span>
          </span>
        </li>
      </ol>

      <div className="bienvenida__accion">
        <button
          type="button"
          className="bienvenida__boton"
          disabled
          aria-describedby="bienvenida-nota"
        >
          Agregar cámara
        </button>
        <p className="bienvenida__nota" id="bienvenida-nota">
          Disponible en la siguiente actualización
        </p>
      </div>
    </section>
  )
}

/** Aviso no bloqueante: el SSE puede seguir vivo aunque falle el HTTP. */
function AvisoResumen({
  error,
  ultimoExitoHttp,
  ultimaActividadSse,
  onReintentar,
}: {
  error: string
  ultimoExitoHttp: Date | null
  ultimaActividadSse: Date | null
  onReintentar: () => void
}) {
  const ahora = useReloj()
  const sseVivo = estaVigente(ultimaActividadSse, ahora)

  return (
    <section className="refresh-error" role="status">
      <div className="refresh-error__body">
        {sseVivo ? (
          <p>
            No se pudo actualizar el resumen HTTP; los eventos en vivo siguen
            llegando.
          </p>
        ) : ultimoExitoHttp ? (
          <p>
            No se pudo actualizar; mostrando datos de{' '}
            <TiempoRelativo ts={ultimoExitoHttp.toISOString()} />.
          </p>
        ) : (
          <p>No se pudo actualizar el resumen HTTP.</p>
        )}
        <p className="refresh-error__detail">{error}</p>
      </div>
      <button
        type="button"
        className="retry-button retry-button--sm"
        onClick={onReintentar}
      >
        Reintentar
      </button>
    </section>
  )
}

/**
 * El reloj del pie vive aquí y no en `App`; usa el store compartido para no
 * crear un intervalo por componente.
 */
function PieEstado({
  ultimoExitoHttp,
  ultimaActividadSse,
  errorResumen,
}: {
  ultimoExitoHttp: Date | null
  ultimaActividadSse: Date | null
  errorResumen: string | null
}) {
  const ahora = useReloj()
  const httpVivo = estaVigente(ultimoExitoHttp, ahora)
  const sseVivo = estaVigente(ultimaActividadSse, ahora)
  const referencia = fechaMasReciente(ultimoExitoHttp, ultimaActividadSse)
  const segundos = referencia
    ? Math.max(0, Math.floor((ahora.getTime() - referencia.getTime()) / 1000))
    : null

  const estado = !referencia
    ? errorResumen
      ? 'Sin conexión'
      : 'Conectando'
    : httpVivo || sseVivo
      ? 'Datos en vivo'
      : 'Datos desactualizados'

  return (
    <footer className="site-footer">
      <p>{estado} · FríoTrack</p>
      {segundos !== null && <p>Actualizado hace {segundos} s</p>}
    </footer>
  )
}

/** Placeholder tranquilo: mismas rejillas y alturas que el contenido real. */
function EsqueletoDashboard() {
  return (
    <div className="dashboard-skeleton" aria-busy="true">
      <p className="visually-hidden" role="status">
        Cargando datos del dashboard…
      </p>

      <div className="dashboard-skeleton__body" aria-hidden="true">
        <section className="section">
          <div className="skeleton skeleton--heading" />
          <div className="kpi-strip">
            {Array.from({ length: 6 }, (_, indice) => (
              <div className="skeleton-kpi" key={indice}>
                <span className="skeleton skeleton--label" />
                <span className="skeleton skeleton--value" />
              </div>
            ))}
          </div>
        </section>

        <section className="section">
          <div className="skeleton skeleton--heading" />
          <div className="skeleton-filters">
            {Array.from({ length: 4 }, (_, indice) => (
              <span className="skeleton skeleton--chip" key={indice} />
            ))}
            <span className="skeleton skeleton--search" />
          </div>
          <div className="camera-grid">
            {Array.from({ length: 5 }, (_, indice) => (
              <div className="skeleton-card" key={indice}>
                <span className="skeleton skeleton--pill" />
                <span className="skeleton skeleton--name" />
                <span className="skeleton skeleton--temperature" />
                <span className="skeleton skeleton--meta" />
                <span className="skeleton skeleton--line" />
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

export default App
