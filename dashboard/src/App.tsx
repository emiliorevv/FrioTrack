import { useState } from 'react'
import './App.css'
import { CameraCard } from './components/CameraCard'
import { FilterBar } from './components/FilterBar'
import { Header } from './components/Header'
import { KpiStrip } from './components/KpiStrip'
import { NotificationToast } from './components/NotificationToast'
import { OnboardingBanner } from './components/OnboardingBanner'
import { SecurityPanel } from './components/SecurityPanel'
import { alertasSeguridad } from './data/mock'
import { useDashboard } from './hooks/useDashboard'
import { useNotificaciones } from './hooks/useNotificaciones'
import { useReloj } from './hooks/useReloj'
import type { FiltroCamaras } from './types'

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
  const {
    health,
    camaras,
    kpis,
    series,
    cargando,
    error,
    actualizadoEn,
    refrescar,
  } = useDashboard()
  const ahora = useReloj()

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
  const actualizadoHaceSegundos = actualizadoEn
    ? Math.max(
        0,
        Math.floor((ahora.getTime() - actualizadoEn.getTime()) / 1000),
      )
    : 0

  return (
    <div className="app">
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>

      <Header
        actualizadoHaceSegundos={actualizadoHaceSegundos}
        escalaTiempo={health?.escala_tiempo}
      />

      <main id="contenido" className="app-main" tabIndex={-1}>
        {cargando && sinDatos ? (
          <EsqueletoDashboard />
        ) : error && sinDatos ? (
          <section className="error-panel" role="alert">
            <h2>No se pudo cargar el dashboard</h2>
            <p>{error}</p>
            <button
              type="button"
              className="retry-button"
              onClick={() => void refrescar()}
            >
              Reintentar
            </button>
          </section>
        ) : (
          <>
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
                      ahora={ahora}
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
              ahora={ahora}
              nota="Datos de ejemplo: el detector SIEM todavía no está conectado."
            />
          </>
        )}
      </main>

      <footer className="site-footer">
        <p>Datos en vivo · FríoTrack</p>
        {actualizadoEn && <p>Actualizado hace {actualizadoHaceSegundos} s</p>}
      </footer>

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
