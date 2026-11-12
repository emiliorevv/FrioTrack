# ADR-0001: PaaS (Render) en lugar de IaaS

- Estado: Aceptado
- Fecha: 2026-11-11
- Módulo: backend

## Contexto
El núcleo de FríoTrack (API, lógica de inventario y alertas) tiene que correr en la nube, estar siempre disponible para la demo y desplegarse cada vez que alguien hace merge a `main`. El equipo es de estudiantes, sin tiempo para administrar servidores, y el presupuesto es cero.

## Decisión
Alojar la API en **Render Web Service** (modelo **PaaS**), con despliegue automático desde la rama `main` de GitHub.

## Alternativas consideradas
| Opción | A favor | En contra |
|---|---|---|
| **Render (PaaS)** | Gratis, despliegue con cada push, HTTPS incluido, logs en el panel | El plan gratis se duerme tras 15 min sin tráfico (lo resuelve ADR-0009) |
| VM en AWS EC2 o Azure (IaaS) | Control total del sistema operativo y la red | Hay que instalar Python, configurar el firewall, poner HTTPS y parchar el servidor; la capa gratuita es de 12 meses y pide tarjeta |
| AWS Lambda o Cloud Functions (FaaS) | Escala solo y cobra por uso | Las conexiones SSE largas no funcionan bien en funciones con tiempo límite |
| Railway (PaaS) | Igual de simple que Render | Ya no tiene plan gratis permanente, solo crédito de prueba |

## Consecuencias
- Nadie del equipo administra servidores; el tiempo se va en el producto.
- La seguridad del sistema operativo y el parcheo los maneja el proveedor (modelo de responsabilidad compartida).
- Dependemos del proveedor: si Render falla durante la demo, no hay plan B automático. Mitigación: probar el despliegue 30 minutos antes de la exposición.
- Si el proyecto creciera a varios restaurantes, se podría pasar a un plan de pago o a contenedores en otra PaaS sin reescribir código, porque la app no depende de nada propio de Render.
