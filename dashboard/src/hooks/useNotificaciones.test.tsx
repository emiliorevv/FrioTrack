import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NotificationToast } from '../components/NotificationToast'
import { StreamProvider } from '../realtime/StreamProvider'
import { EventSourceFalso } from '../test/EventSourceFalso'
import type { Notificacion } from '../types'
import { MAX_NOTIFICACIONES, useNotificaciones } from './useNotificaciones'

const NOTIFICACION: Notificacion = {
  canal: 'simulado',
  tipo: 'alerta_temperatura',
  camara_id: 1,
  mensaje:
    'FríoTrack: Cámara Pescados y mariscos a 3.4 °C hace 10 min. $4,850 en riesgo.',
  ts: '2026-11-18T19:05:00+00:00',
  url: 'http://localhost:5173',
}

function conMensaje(mensaje: string): Notificacion {
  return { ...NOTIFICACION, mensaje }
}

function Prueba() {
  const { notificacion, cerrar } = useNotificaciones()

  return (
    <div>
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

function renderizar() {
  return render(
    <StreamProvider>
      <Prueba />
    </StreamProvider>,
  )
}

function emitir(notificacion: Notificacion) {
  act(() => {
    EventSourceFalso.instancias[0]?.emitir('notificacion', notificacion)
  })
}

beforeEach(() => {
  EventSourceFalso.reiniciar()
  vi.stubGlobal('EventSource', EventSourceFalso)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useNotificaciones', () => {
  it('muestra la primera notificación y al cerrar pasa a la siguiente', () => {
    renderizar()

    emitir(conMensaje('primera'))
    expect(screen.getByRole('alert')).toHaveTextContent('primera')

    emitir(conMensaje('segunda'))
    expect(screen.getByRole('alert')).toHaveTextContent('primera')
    expect(screen.queryByText('segunda')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar notificación' }))

    expect(screen.getByRole('alert')).toHaveTextContent('segunda')
  })

  it('con la cola llena conserva el toast visible y descarta el pendiente más antiguo', () => {
    renderizar()

    for (const mensaje of ['A', 'B', 'C', 'D', 'E']) {
      emitir(conMensaje(mensaje))
    }
    expect(screen.getByText('A')).toBeInTheDocument()

    emitir(conMensaje('F'))
    emitir(conMensaje('G'))

    expect(screen.getByText('A')).toBeInTheDocument()

    const visibles: string[] = []
    for (let cierre = 0; cierre < MAX_NOTIFICACIONES; cierre += 1) {
      const toast = screen.getByRole('alert')
      visibles.push(toast.querySelector('.toast__message')?.textContent ?? '')
      fireEvent.click(
        screen.getByRole('button', { name: 'Cerrar notificación' }),
      )
    }

    expect(visibles).toEqual(['A', 'D', 'E', 'F', 'G'])
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('ignora una notificación con un tipo desconocido', () => {
    renderizar()

    act(() => {
      EventSourceFalso.instancias[0]?.emitir('notificacion', {
        ...NOTIFICACION,
        tipo: 'otro',
      })
    })

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('ignora eventos que no son notificacion', () => {
    renderizar()

    act(() => {
      EventSourceFalso.instancias[0]?.emitir('kpis', { alertas_activas: 2 })
      EventSourceFalso.instancias[0]?.emitir('lectura', { temperatura_c: 3.4 })
    })

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('no revienta si no hay EventSource', () => {
    vi.stubGlobal('EventSource', undefined)

    expect(() => renderizar()).not.toThrow()
  })
})
