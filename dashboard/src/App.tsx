import { useState } from 'react'
import './App.css'
import { useAuth } from './auth/AuthProvider'
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

function App() {
  const [filtro, setFiltro] = useState<FiltroCamaras>('todas')
  const [busqueda, setBusqueda] = useState('')
  const { notificacion, cerrar } = useNotificaciones()
  const auth = useAuth()
  const usuario = auth.usuario ?? 'Usuario'
  const rol = auth.rol ?? ''
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
        onLogout={auth.logout}
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

            <OnboardingBanner />

            <section className="section" aria-labelledby="resumen-title">
              <div className="section-heading">
                <div>
                  <h2 id="resumen-title">Resumen de hoy</h2>
                  <p>Últimas 24 horas · turno de comida</p>
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
              puedeAtender={rol === 'jefe_cocina'}
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

              <FilterBar
                filtro={filtro}
                onFiltro={setFiltro}
                busqueda={busqueda}
                onBusqueda={setBusqueda}
                conteos={conteos}
                visibles={camarasFiltradas.length}
              />

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
              ) : (
                <p className="empty-state">
                  {camaras.length === 0
                    ? 'Todavía no hay cámaras registradas.'
                    : 'No hay cámaras que coincidan con el filtro.'}
                </p>
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
