import { useState } from 'react'
import './App.css'
import { CameraCard } from './components/CameraCard'
import { FilterBar } from './components/FilterBar'
import { Header } from './components/Header'
import { KpiStrip } from './components/KpiStrip'
import { NotificationToast } from './components/NotificationToast'
import { OnboardingBanner } from './components/OnboardingBanner'
import { SecurityPanel } from './components/SecurityPanel'
import { useNotificaciones } from './hooks/useNotificaciones'
import {
  AHORA_DEMO,
  actualizadoHaceSegundos,
  alertasSeguridad,
  camaras,
  kpis,
  seriesCamaras,
} from './data/mock'
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

  return (
    <div className="app">
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>

      {/* La escala vendrá de GET /api/health; mientras no haya API, la demo corre a ×30. */}
      <Header
        actualizadoHaceSegundos={actualizadoHaceSegundos}
        escalaTiempo={30}
      />

      <main id="contenido" className="app-main">
        <OnboardingBanner />

        <section className="section" aria-labelledby="resumen-title">
          <div className="section-heading">
            <div>
              <h2 id="resumen-title">Resumen de hoy</h2>
              <p>Últimas 24 horas · turno de comida</p>
            </div>
          </div>
          <KpiStrip kpis={kpis} />
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
                  serie={seriesCamaras[camara.id] ?? []}
                  ahora={AHORA_DEMO}
                />
              ))}
            </div>
          ) : (
            <p className="empty-state">
              No hay cámaras que coincidan con el filtro.
            </p>
          )}
        </section>

        <SecurityPanel alertas={alertasSeguridad} ahora={AHORA_DEMO} />
      </main>

      <footer className="site-footer">
        <p>Datos simulados · FríoTrack Alfa</p>
      </footer>

      {notificacion && (
        <NotificationToast
          key={notificacion.ts}
          notificacion={notificacion}
          onCerrar={cerrar}
        />
      )}
    </div>
  )
}

export default App
