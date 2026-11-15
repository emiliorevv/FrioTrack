import { formatearTemperatura } from './format'
import type { AccionSeguridad, AlertaSeguridad } from '../types'

const ID_FUERZA_BRUTA = '3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41'
const ID_TOKEN_DESCONOCIDO = 'e26aa409-804c-47fb-b852-1786ddaa172d'
const ID_LECTURAS_IMPOSIBLES = '26f277c2-6d7a-4ff2-b44c-452f2788f824'

const ETIQUETA_ACCION: Record<AccionSeguridad, string> = {
  bloquear_ip: 'IP bloqueada',
  revocar_token: 'Token revocado',
  marcar_lecturas: 'Lecturas marcadas',
}

export interface ReglaSiem {
  id: string
  explicacion: (alerta: AlertaSeguridad) => string
  /** Clave de `detalle` que contiene la ventana de detección, si aplica. */
  campoVentana?: string
}

/**
 * El backend es la fuente de verdad; esto es copy de UI y fallback hasta que
 * `/seguridad/alertas` envíe la descripción. Los `descripcion` de la API o
 * de `detalle` tienen prioridad.
 */
export const REGLAS_SIEM: ReglaSiem[] = [
  {
    id: ID_FUERZA_BRUTA,
    campoVentana: 'ventana_s',
    explicacion: () =>
      'Detectamos muchos intentos rechazados seguidos desde la misma dirección (inicios de sesión o envíos de telemetría). Para proteger el sistema, bloqueamos esa IP durante el tiempo configurado.',
  },
  {
    id: ID_TOKEN_DESCONOCIDO,
    explicacion: (alerta) => {
      const sensor = sensorDeDetalle(alerta)
      if (sensor && alerta.accion === 'revocar_token') {
        return `El sensor ${sensor} autenticó una lectura desde una red desconocida. Revocamos su token para evitar lecturas falsas.`
      }
      if (!sensor) {
        return 'Detectamos un token de sensor usado desde una red desconocida, pero la alerta no identificó el sensor; no se revocó ningún token. Revisa los accesos recientes.'
      }
      return `El sensor ${sensor} autenticó una lectura desde una red desconocida. La acción registrada fue: ${etiquetaAccion(alerta.accion)}.`
    },
  },
  {
    id: ID_LECTURAS_IMPOSIBLES,
    explicacion: () =>
      'Una cámara reportó un cambio de temperatura demasiado grande en muy poco tiempo. Marcamos esas lecturas como sospechosas para revisarlas.',
  },
]

export interface DatoAlerta {
  etiqueta: string
  valor: string
}

export function explicacionDeAlerta(alerta: AlertaSeguridad): string {
  const descripcionApi =
    alerta.descripcion?.trim() ||
    textoDeDetalle(alerta.detalle.descripcion)?.trim() ||
    ''

  if (descripcionApi) {
    return descripcionApi
  }

  const regla = REGLAS_SIEM.find((item) => item.id === alerta.regla_id)
  return (
    regla?.explicacion(alerta) ??
    `El detector marcó esta actividad como sospechosa: ${alerta.regla}. Revisa la alerta y confirma si fue esperada.`
  )
}

/** Acción efectiva: no afirmes una revocación que el detector no pudo hacer. */
export function etiquetaAccionDeAlerta(alerta: AlertaSeguridad): string {
  if (
    alerta.regla_id === ID_TOKEN_DESCONOCIDO &&
    !sensorDeDetalle(alerta) &&
    alerta.accion === 'revocar_token'
  ) {
    return 'Sin revocación'
  }
  return etiquetaAccion(alerta.accion)
}

/** Datos concretos del `detalle` para el desplegable, sin claves internas. */
export function datosDeAlerta(alerta: AlertaSeguridad): DatoAlerta[] {
  const datos: DatoAlerta[] = []
  const agregar = (etiqueta: string, valor: string | null) => {
    if (valor !== null) {
      datos.push({ etiqueta, valor })
    }
  }

  agregar('IP', alerta.ip_origen)
  agregar('Intentos', textoDeDetalle(alerta.detalle.intentos))
  agregar('Sensor', sensorDeDetalle(alerta))
  agregar('Cámara', textoDeDetalle(alerta.detalle.camara_id))

  const rutas = rutasDeDetalle(alerta.detalle)
  if (rutas.length > 0) {
    agregar('Rutas', rutas.join(', '))
  }

  const regla = REGLAS_SIEM.find((item) => item.id === alerta.regla_id)
  if (regla?.campoVentana) {
    agregar('Ventana', ventanaEnMinutos(alerta.detalle[regla.campoVentana]))
  }

  const anterior = numeroDeDetalle(alerta.detalle.temperatura_anterior_c)
  if (anterior !== null) {
    agregar('Temperatura anterior', `${formatearTemperatura(anterior)} °C`)
  }

  const actual = numeroDeDetalle(alerta.detalle.temperatura_c)
  if (actual !== null) {
    agregar('Temperatura', `${formatearTemperatura(actual)} °C`)
  }

  const delta = numeroDeDetalle(alerta.detalle.delta_c)
  if (delta !== null) {
    agregar('Delta', `${formatearTemperatura(delta)} °C`)
  }

  const segundos = textoDeDetalle(alerta.detalle.segundos)
  if (segundos !== null) {
    agregar('Intervalo', `${segundos} s`)
  }

  agregar('Acción', etiquetaAccionDeAlerta(alerta))
  return datos
}

function etiquetaAccion(valor: string): string {
  return (ETIQUETA_ACCION as Record<string, string>)[valor] ?? 'Sin acción'
}

function sensorDeDetalle(alerta: AlertaSeguridad): string | null {
  return textoDeDetalle(alerta.detalle.sensor_id)
}

function textoDeDetalle(valor: unknown): string | null {
  if (typeof valor === 'string' && valor.trim()) {
    return valor.trim()
  }
  if (typeof valor === 'number' && Number.isFinite(valor)) {
    return String(valor)
  }
  return null
}

function numeroDeDetalle(valor: unknown): number | null {
  if (typeof valor === 'number' && Number.isFinite(valor)) {
    return valor
  }
  if (typeof valor === 'string' && valor.trim()) {
    const numero = Number(valor)
    return Number.isFinite(numero) ? numero : null
  }
  return null
}

function ventanaEnMinutos(valor: unknown): string | null {
  const segundos = numeroDeDetalle(valor)
  if (segundos === null) {
    return null
  }
  const minutos = segundos / 60
  return `${Number.isInteger(minutos) ? minutos : minutos.toFixed(1)} min`
}

function rutasDeDetalle(detalle: Record<string, unknown>): string[] {
  const rutas = detalle.rutas
  if (!Array.isArray(rutas)) {
    return []
  }
  return rutas.filter(
    (ruta): ruta is string => typeof ruta === 'string' && ruta.trim() !== '',
  )
}
