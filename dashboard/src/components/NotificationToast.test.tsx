import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Notificacion, TipoNotificacion } from '../types'
import { NotificationToast } from './NotificationToast'

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

describe('NotificationToast', () => {
  it('muestra la etiqueta, el título y el mensaje de la notificación', () => {
    render(
      <NotificationToast
        notificacion={crearNotificacion()}
        onCerrar={() => {}}
      />,
    )

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

  it('se anuncia como status polite sin robar el foco', () => {
    render(
      <NotificationToast
        notificacion={crearNotificacion()}
        onCerrar={() => {}}
      />,
    )

    const toast = screen.getByRole('status')
    expect(toast).toHaveAttribute('aria-live', 'polite')
    expect(
      screen.getByRole('button', { name: 'Cerrar notificación' }),
    ).not.toHaveFocus()
  })

  it('cierra con el botón', () => {
    const onCerrar = vi.fn()
    render(
      <NotificationToast
        notificacion={crearNotificacion()}
        onCerrar={onCerrar}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar notificación' }))

    expect(onCerrar).toHaveBeenCalledTimes(1)
  })
})
