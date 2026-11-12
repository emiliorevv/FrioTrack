# ADR-0004: Tiempo real con Server-Sent Events

- Estado: Aceptado
- Fecha: 2026-11-11
- Módulo: backend, dashboard

## Contexto
La rúbrica pide que el dashboard actualice los KPIs en tiempo real sin recargar. Los datos solo viajan en una dirección: del backend al dashboard.

## Decisión
La API expone **`GET /api/stream`** con **Server-Sent Events**. El dashboard abre la conexión con `EventSource` y recibe los eventos `lectura`, `alerta_abierta`, `alerta_cerrada`, `lote_actualizado` y `kpis` (detalle en el contrato de la API).

Cómo funciona por dentro:
1. Llega una lectura a `POST /telemetria`.
2. Se guarda en Postgres y se aplican las reglas de negocio.
3. El resultado se publica en una cola en memoria (`asyncio.Queue` por cliente conectado).
4. Cada conexión de `/stream` lee su cola y escribe `event: ...` / `data: ...` al navegador.

## Alternativas consideradas
| Opción | A favor | En contra |
|---|---|---|
| **SSE** | HTTP normal, el navegador se reconecta solo, muy poco código en FastAPI y en React | Solo va de servidor a cliente (justo lo que necesitamos); `EventSource` no deja mandar headers, el token va en la URL |
| WebSockets | Bidireccional | Más código y manejo de reconexión a mano para algo que no necesita ida y vuelta |
| Polling cada N segundos | Lo más simple | No es tiempo real; la rúbrica baja a 80 % si "requiere recarga" |
| Supabase Realtime | Ya viene con la base | El dashboard dependería directo de la base y no de la API, saltándose la autenticación y los logs |

## Consecuencias
- La cola en memoria solo funciona con **una instancia** de la API, que es lo que tenemos. Con varias instancias habría que usar `LISTEN/NOTIFY` de Postgres o Redis.
- El token en la URL es de corta duración y se registra en los logs sin el valor completo.
