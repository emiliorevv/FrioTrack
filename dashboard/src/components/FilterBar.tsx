import type { FiltroCamaras } from '../types'

const FILTROS: { id: FiltroCamaras; label: string }[] = [
  { id: 'todas', label: 'Todas' },
  { id: 'en_rango', label: 'En rango' },
  { id: 'alerta', label: 'Alerta' },
  { id: 'critica', label: 'Crítica' },
]

interface FilterBarProps {
  filtro: FiltroCamaras
  onFiltro: (filtro: FiltroCamaras) => void
  busqueda: string
  onBusqueda: (valor: string) => void
  conteos: Record<FiltroCamaras, number>
  visibles: number
}

export function FilterBar({
  filtro,
  onFiltro,
  busqueda,
  onBusqueda,
  conteos,
  visibles,
}: FilterBarProps) {
  return (
    <div className="filter-bar">
      <div className="chips" role="group" aria-label="Filtrar por estado">
        {FILTROS.map((opcion) => (
          <button
            key={opcion.id}
            type="button"
            className="chip"
            aria-pressed={filtro === opcion.id}
            onClick={() => onFiltro(opcion.id)}
          >
            {opcion.label}{' '}
            <span className="chip__count">({conteos[opcion.id]})</span>
          </button>
        ))}
      </div>

      <label className="search">
        <span className="visually-hidden">Buscar cámara</span>
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
          onChange={(evento) => onBusqueda(evento.target.value)}
          placeholder="Buscar cámara…"
          autoComplete="off"
        />
      </label>

      <p className="visually-hidden" role="status">
        {visibles} de {conteos.todas} cámaras visibles
      </p>
    </div>
  )
}
