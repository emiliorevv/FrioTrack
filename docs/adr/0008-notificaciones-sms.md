# ADR-0008: Alertas por SMS con Twilio

- Estado: Aceptado
- Fecha: 2026-11-11
- Módulo: backend

## Contexto
El jefe de cocina tiene que enterarse de una alerta aunque no tenga el dashboard abierto, esté fuera del restaurante o sea de noche. No vamos a hacer app nativa (ADR-0005).

## Decisión
Mandar las alertas por **SMS con Twilio** desde la API. Se manda **un SMS al abrir la alerta** y **otro si los lotes pasan a merma**; nunca uno por lectura. El mensaje incluye la cámara, la temperatura, el valor en riesgo y el link al dashboard.

Ejemplo: `FríoTrack: Cámara Pescados a 3.4 °C hace 10 min. $4,850 en riesgo. Ver: https://friotrack.vercel.app`

## Alternativas consideradas
| Opción | A favor | En contra |
|---|---|---|
| **SMS (Twilio)** | Llega a cualquier celular sin instalar nada ni tener internet; unas 10 líneas de código | Cuesta por mensaje en producción; la cuenta de prueba solo manda a números verificados |
| Web Push (PWA) | Gratis | En iPhone solo funciona si el dashboard se agrega a la pantalla de inicio; más configuración (service worker, llaves VAPID) |
| WhatsApp (Twilio o Meta) | Lo que más se usa en México | Requiere plantillas aprobadas y número de negocio; el sandbox pide que cada número se una con un código |
| Bot de Telegram | Gratis y fácil | Casi nadie en un restaurante usa Telegram |
| Correo | Gratis | Nadie ve un correo a las 3 de la mañana |

## Consecuencias
- Para la demo se usa la cuenta de prueba de Twilio con crédito gratis; se verifican los celulares del equipo (y el del profe si se quiere mostrar en vivo). Los mensajes llevan el prefijo "Sent from your Twilio trial account".
- Las credenciales de Twilio van en variables de entorno de Render.
- Si Twilio falla, la alerta sigue en el dashboard; el envío de SMS no puede tumbar la ingesta (se hace en segundo plano).
