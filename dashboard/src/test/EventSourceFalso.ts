export type OyenteSSE = (evento: MessageEvent<string>) => void

/** EventSource mínimo: guarda oyentes y permite emitir/fallar desde el test. */
export class EventSourceFalso {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  static instancias: EventSourceFalso[] = []

  readonly url: string
  readyState = EventSourceFalso.CONNECTING
  cerrado = false
  onerror: ((evento: Event) => void) | null = null
  onopen: ((evento: Event) => void) | null = null
  private oyentes = new Map<string, Set<OyenteSSE>>()

  constructor(url: string) {
    this.url = url
    EventSourceFalso.instancias.push(this)
  }

  static reiniciar() {
    EventSourceFalso.instancias = []
  }

  addEventListener(tipo: string, oyente: OyenteSSE) {
    const conjunto = this.oyentes.get(tipo) ?? new Set<OyenteSSE>()
    conjunto.add(oyente)
    this.oyentes.set(tipo, conjunto)
  }

  removeEventListener(tipo: string, oyente: OyenteSSE) {
    this.oyentes.get(tipo)?.delete(oyente)
  }

  close() {
    this.cerrado = true
    this.readyState = EventSourceFalso.CLOSED
  }

  emitir(tipo: string, datos: unknown) {
    const evento = new MessageEvent(tipo, { data: JSON.stringify(datos) })
    for (const oyente of [...(this.oyentes.get(tipo) ?? [])]) {
      oyente(evento)
    }
  }

  simularError(readyState = EventSourceFalso.CLOSED) {
    this.readyState = readyState
    this.onerror?.(new Event('error'))
  }

  simularApertura() {
    this.readyState = EventSourceFalso.OPEN
    this.onopen?.(new Event('open'))
  }
}
