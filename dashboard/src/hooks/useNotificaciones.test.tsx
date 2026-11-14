import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Notificacion } from '../types'
import { NotificationToast } from '../components/NotificationToast'
import {
  DURACION_NOTIFICACION_MS,
  useNotificaciones,
} from './useNotificaciones'

type Oyente = (evento: MessageEvent<string>) => void

/** EventSource mínimo: guarda oyentes y permite emitir eventos desde el test. */
class EventSourceFalso {
  static instancias: EventSourceFalso[] = []

  readonly url: string
  cerrado = false
  private oyentes = new Map<string, Set<Oyente>>()

  constructor(url: string) {
    this.url = url
    EventSourceFalso.instancias.push(this)
  }

  addEventListener(tipo: string, oyente: Oyente) {
    const conjunto = this.oyentes.get(tipo) ?? new Set<Oyente>()
    conjunto.add(oyente)
    this.oyentes.set(tipo, conjunto)
  }

  removeEventListener(tipo: string, oyente: Oyente) {
    this.oyentes.get(tipo)?.delete(oyente)
  }

  close() {
    this.cerrado = true
  }

  emitir(tipo: string, datos: unknown) {
    const evento = new MessageEvent(tipo, { data: JSON.stringify(datos) })
    for (const oyente of this.oyentes.get(tipo) ?? []) {
      oyente(evento)
    }
  }
}

const NOTIFICACION: Notificacion = {
  canal: 'simulado',
  tipo: 'alerta_temperatura',
  camara_id: 1,
  mensaje:
    'FríoTrack: Cámara Pescados y mariscos a 3.4 °C hace 10 min. $4,850 en riesgo.',
  ts: '2026-11-18T19:05:00+00:00',
  url: 'http://localhost:5173',
}

function Prueba() {
  const { notificacion, cerrar } = useNotificaciones()

  return (
    <div>
      <button type="button" onClick={cerrar}>
        cerrar desde la prueba
      </button>
      {notificacion && (
        <NotificationToast notificacion={notificacion} onCerrar={cerrar} />
      )}
    </div>
  )
}

function emitirNotificacion() {
  act(() => {
    EventSourceFalso.instancias[0]?.emitir('notificacion', NOTIFICACION)
  })
}

beforeEach(() => {
  EventSourceFalso.instancias = []
  vi.stubGlobal('EventSource', EventSourceFalso)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useNotificaciones', () => {
  it('abre el stream en la URL de la API', () => {
    render(<Prueba />)

    const base = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000/api'
    expect(EventSourceFalso.instancias).toHaveLength(1)
    expect(EventSourceFalso.instancias[0]?.url).toBe(`${base}/stream`)
  })

  it('muestra el toast al recibir una notificación y lo quita con cerrar', () => {
    render(<Prueba />)
    emitirNotificacion()

    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText(NOTIFICACION.mensaje)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar notificación' }))

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('ignora eventos que no son notificacion', () => {
    render(<Prueba />)

    act(() => {
      EventSourceFalso.instancias[0]?.emitir('kpis', { alertas_activas: 2 })
      EventSourceFalso.instancias[0]?.emitir('lectura', { temperatura_c: 3.4 })
    })

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('cierra el EventSource al desmontar', () => {
    const { unmount } = render(<Prueba />)
    const fuente = EventSourceFalso.instancias[0]

    unmount()

    expect(fuente?.cerrado).toBe(true)
  })

  it('descarta el toast a los 10 segundos', () => {
    vi.useFakeTimers()
    render(<Prueba />)
    emitirNotificacion()

    expect(screen.getByRole('status')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(DURACION_NOTIFICACION_MS)
    })

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('no revienta si no hay EventSource', () => {
    vi.stubGlobal('EventSource', undefined)

    expect(() => render(<Prueba />)).not.toThrow()
  })
})
