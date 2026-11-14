import { useState } from 'react'
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EventSourceFalso } from '../test/EventSourceFalso'
import { construirUrlStream, RECONEXION_MS, type EventoStream } from './stream'
import { StreamProvider, useStreamEvent } from './StreamProvider'

const API = 'https://api.prueba.mx/api'

function Escucha({ evento, nombre }: { evento: EventoStream; nombre: string }) {
  const [ultimo, setUltimo] = useState('')
  useStreamEvent(evento, (mensaje) => setUltimo(mensaje.data))
  return <p data-testid={nombre}>{ultimo}</p>
}

beforeEach(() => {
  EventSourceFalso.reiniciar()
  vi.stubGlobal('EventSource', EventSourceFalso)
  vi.stubEnv('VITE_API_URL', API)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.useRealTimers()
})

describe('StreamProvider', () => {
  it('comparte una sola conexión y despacha cada evento a sus oyentes', () => {
    render(
      <StreamProvider>
        <Escucha evento="notificacion" nombre="notificacion-a" />
        <Escucha evento="notificacion" nombre="notificacion-b" />
        <Escucha evento="kpis" nombre="kpis" />
      </StreamProvider>,
    )

    expect(EventSourceFalso.instancias).toHaveLength(1)

    act(() => {
      EventSourceFalso.instancias[0]?.emitir('notificacion', {
        mensaje: 'algo pasó',
      })
    })

    expect(screen.getByTestId('notificacion-a')).toHaveTextContent('algo pasó')
    expect(screen.getByTestId('notificacion-b')).toHaveTextContent('algo pasó')
    expect(screen.getByTestId('kpis')).toBeEmptyDOMElement()

    act(() => {
      EventSourceFalso.instancias[0]?.emitir('kpis', { alertas_activas: 2 })
    })

    expect(screen.getByTestId('kpis')).toHaveTextContent('alertas_activas')
    expect(screen.getByTestId('notificacion-a')).not.toHaveTextContent(
      'alertas_activas',
    )
  })

  it('arma la URL con el token cuando existe', () => {
    render(
      <StreamProvider token="jwt con espacios">
        <p>contenido</p>
      </StreamProvider>,
    )

    expect(EventSourceFalso.instancias[0]?.url).toBe(
      construirUrlStream(API, 'jwt con espacios'),
    )
  })

  it('reconecta a los 5 s cuando el stream quedó CLOSED', () => {
    vi.useFakeTimers()
    render(
      <StreamProvider>
        <p>contenido</p>
      </StreamProvider>,
    )

    expect(EventSourceFalso.instancias).toHaveLength(1)
    const primera = EventSourceFalso.instancias[0]

    act(() => primera?.simularError(EventSourceFalso.CLOSED))
    expect(EventSourceFalso.instancias).toHaveLength(1)

    act(() => vi.advanceTimersByTime(RECONEXION_MS))

    expect(EventSourceFalso.instancias).toHaveLength(2)
    expect(primera?.cerrado).toBe(true)
  })

  it('no reconecta si el stream sigue CONNECTING (reintenta el navegador)', () => {
    vi.useFakeTimers()
    render(
      <StreamProvider>
        <p>contenido</p>
      </StreamProvider>,
    )

    act(() =>
      EventSourceFalso.instancias[0]?.simularError(EventSourceFalso.CONNECTING),
    )
    act(() => vi.advanceTimersByTime(RECONEXION_MS))

    expect(EventSourceFalso.instancias).toHaveLength(1)
  })

  it('cierra la conexión y cancela la reconexión pendiente al desmontar', () => {
    vi.useFakeTimers()
    const { unmount } = render(
      <StreamProvider>
        <p>contenido</p>
      </StreamProvider>,
    )
    const fuente = EventSourceFalso.instancias[0]

    act(() => fuente?.simularError(EventSourceFalso.CLOSED))
    unmount()
    act(() => vi.advanceTimersByTime(RECONEXION_MS))

    expect(fuente?.cerrado).toBe(true)
    expect(EventSourceFalso.instancias).toHaveLength(1)
  })

  it('deja de despachar a un oyente que se desmonta', () => {
    const oyente = vi.fn()

    function Hijo({ visible }: { visible: boolean }) {
      return visible ? <EscuchaConSpy evento="lectura" oyente={oyente} /> : null
    }

    const { rerender } = render(
      <StreamProvider>
        <Hijo visible />
      </StreamProvider>,
    )

    act(() => {
      EventSourceFalso.instancias[0]?.emitir('lectura', { temperatura_c: 4 })
    })
    expect(oyente).toHaveBeenCalledTimes(1)

    rerender(
      <StreamProvider>
        <Hijo visible={false} />
      </StreamProvider>,
    )
    act(() => {
      EventSourceFalso.instancias[0]?.emitir('lectura', { temperatura_c: 5 })
    })

    expect(oyente).toHaveBeenCalledTimes(1)
    expect(EventSourceFalso.instancias).toHaveLength(1)
  })
})

function EscuchaConSpy({
  evento,
  oyente,
}: {
  evento: EventoStream
  oyente: (mensaje: MessageEvent<string>) => void
}) {
  useStreamEvent(evento, oyente)
  return null
}
