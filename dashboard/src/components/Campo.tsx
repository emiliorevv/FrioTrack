import type { ReactNode } from 'react'

interface CampoProps {
  id: string
  etiqueta: string
  error?: string
  ayuda: string
  children: ReactNode
}

/** Campo de formulario con label, ayuda y error asociado por `aria-describedby`. */
export function Campo({ id, etiqueta, error, ayuda, children }: CampoProps) {
  return (
    <div className={`campo${error ? ' campo--error' : ''}`}>
      <label className="campo__label" htmlFor={id}>
        {etiqueta}
      </label>
      {children}
      {error ? (
        <p className="campo__error" id={`${id}-error`} role="alert">
          {error}
        </p>
      ) : (
        <p className="campo__ayuda" id={`${id}-ayuda`}>
          {ayuda}
        </p>
      )}
    </div>
  )
}
