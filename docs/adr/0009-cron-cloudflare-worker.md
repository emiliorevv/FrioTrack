# ADR-0009: Flujo continuo con Cloudflare Worker

- Estado: Aceptado
- Fecha: 2026-11-11
- Módulo: backend

## Contexto
La rúbrica pide flujo de procesamiento continuo, no datos estáticos. El plan gratis de Render no incluye workers en segundo plano y además apaga la API tras 15 minutos sin tráfico, así que si nadie corre el simulador, el dashboard se queda vacío y la primera petición tarda casi un minuto en despertar el servicio.

## Decisión
Un **Cloudflare Worker con Cron Trigger** (plan gratis) llama cada minuto a **`POST /api/simulador/tick`** con su propio token. La API genera una lectura normal por cámara y la procesa igual que una lectura real.

El simulador en la laptop sigue siendo el gateway del restaurante: es el que manda lecturas cada pocos segundos durante la demo y donde se provocan las fallas (`puerta_abierta`, `falla_compresor`).

## Alternativas consideradas
| Opción | A favor | En contra |
|---|---|---|
| **Cloudflare Worker con cron** | Gratis, cada minuto, unas 15 líneas; mantiene despierta la API | Otro servicio más; la lógica del simulador se queda en Python y el Worker solo dispara |
| Background worker de Render | Todo en un proveedor | No es gratis |
| GitHub Actions con cron | Gratis | Mínimo cada 5 minutos y sin garantía de puntualidad |
| Tarea en segundo plano dentro de la API | Nada extra | No corre mientras Render tiene la API dormida |
| Laptop prendida todo el tiempo | Lo más simple | No es despliegue en la nube y se cae si se apaga |

## Consecuencias
- Siempre hay datos recientes y la API responde rápido en la demo.
- El token del cron solo puede llamar a `/simulador/tick` (mínimo privilegio, ADR-0006).
- 1,440 llamadas al día, muy por debajo del límite gratis de Cloudflare.
