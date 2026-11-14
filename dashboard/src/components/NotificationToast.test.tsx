import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Notificacion, TipoNotificacion } from '../types'
import {
  DURACION_NOTIFICACION_MS,
  NotificationToast,
} from './NotificationToast'

const MENSAJE =
  'FríoTrack: Cámara Pescados y mariscos a 3.4 °C hace 10 min. $4,850 en riesgo.'

function crearNotificacion(
  tipo: TipoNotificacion = 'alerta_temperatura',
): Notificacion {
  return {
    canal: 'simulado',
    tipo,
    camara_id: 1,
    mensaje: MENSAJE,
    ts: '2026-11-18T19:05:00+00:00',
    url: 'http://localhost:5173',
  }
}

function renderizar(onCerrar = vi.fn()) {
  render(
    <NotificationToast
      notificacion={crearNotificacion()}
      onCerrar={onCerrar}
    />,
  )
  return screen.getByRole('alert')
}

afterEach(() => {
  vi.useRealTimers()
})

describe('NotificationToast', () => {
  it('muestra la etiqueta, el título y el mensaje de la notificación', () => {
    renderizar()

    expect(screen.getByText('Notificación simulada')).toBeInTheDocument()
    expect(screen.getByText('Alerta de temperatura')).toBeInTheDocument()
    expect(screen.getByText(MENSAJE)).toBeInTheDocument()
  })

  it.each<[TipoNotificacion, string]>([
    ['alerta_temperatura', 'Alerta de temperatura'],
    ['alerta_puerta', 'Alerta de puerta'],
    ['merma', 'Producto en merma'],
  ])('usa el título de %s', (tipo, titulo) => {
    render(
      <NotificationToast
        notificacion={crearNotificacion(tipo)}
        onCerrar={() => {}}
      />,
    )

    expect(screen.getByText(titulo)).toBeInTheDocument()
  })

  it('se anuncia como alert atómico sin robar el foco', () => {
    renderizar()

    const toast = screen.getByRole('alert')
    expect(toast).toHaveAttribute('aria-atomic', 'true')
    expect(
      screen.getByRole('button', { name: 'Cerrar notificación' }),
    ).not.toHaveFocus()
  })

  it('cierra con el botón', () => {
    const onCerrar = vi.fn()
    renderizar(onCerrar)

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar notificación' }))

    expect(onCerrar).toHaveBeenCalledTimes(1)
  })

  it('se cierra solo a los 10 segundos', () => {
    vi.useFakeTimers()
    const onCerrar = vi.fn()
    renderizar(onCerrar)

    act(() => vi.advanceTimersByTime(DURACION_NOTIFICACION_MS - 1))
    expect(onCerrar).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(1))
    expect(onCerrar).toHaveBeenCalledTimes(1)
  })

  it('pausa el auto-cierre con el mouse encima y lo reanuda al salir', () => {
    vi.useFakeTimers()
    const onCerrar = vi.fn()
    const toast = renderizar(onCerrar)

    act(() => vi.advanceTimersByTime(4_000))
    fireEvent.mouseEnter(toast)

    act(() => vi.advanceTimersByTime(20_000))
    expect(onCerrar).not.toHaveBeenCalled()

    fireEvent.mouseLeave(toast)
    act(() => vi.advanceTimersByTime(DURACION_NOTIFICACION_MS - 4_000 - 1))
    expect(onCerrar).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(1))
    expect(onCerrar).toHaveBeenCalledTimes(1)
  })

  it('pausa el auto-cierre mientras el foco está dentro', () => {
    vi.useFakeTimers()
    const onCerrar = vi.fn()
    renderizar(onCerrar)
    const boton = screen.getByRole('button', { name: 'Cerrar notificación' })

    act(() => vi.advanceTimersByTime(4_000))
    fireEvent.focusIn(boton)

    act(() => vi.advanceTimersByTime(20_000))
    expect(onCerrar).not.toHaveBeenCalled()

    fireEvent.focusOut(boton)
    act(() => vi.advanceTimersByTime(DURACION_NOTIFICACION_MS - 4_000 - 1))
    expect(onCerrar).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(1))
    expect(onCerrar).toHaveBeenCalledTimes(1)
  })
})
