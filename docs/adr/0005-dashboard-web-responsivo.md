# ADR-0005: Dashboard web responsivo en lugar de app nativa

- Estado: Aceptado
- Fecha: 2026-11-11
- Módulo: dashboard

## Contexto
El jefe de cocina y el gerente tienen que poder ver el estado de las cámaras desde el celular, dentro y fuera del restaurante (Tema 3.4). También se usa en una laptop o tablet en la cocina.

## Decisión
Un **dashboard web en React + Vite, responsivo** (pensado primero para celular), desplegado en **Vercel**. Las alertas urgentes llegan por SMS (ADR-0008) con un link directo al dashboard.

## Alternativas consideradas
| Opción | A favor | En contra |
|---|---|---|
| **Web responsiva** | Un solo código para celular, tablet y laptop; se abre con un link, sin instalar nada; se despliega gratis | Sin acceso a funciones nativas del teléfono (no las necesitamos) |
| App nativa (Kotlin / Swift) | Mejor integración con el teléfono | Dos códigos, publicación en tiendas, imposible en una semana |
| React Native / Flutter | Un código para Android e iOS | Hay que instalarla en cada celular para la demo; el profe no la puede abrir con un link |
| Grafana | Gráficas listas | Poco control del diseño móvil y de la lógica de lotes; parece herramienta y no producto |

## Consecuencias
- Cualquiera abre el dashboard escaneando un QR en la exposición, lo que demuestra la supervisión remota.
- El dashboard solo habla con la API por el contrato; no toca la base de datos.
- La URL de la API va en una variable de entorno de Vercel (`VITE_API_URL`).
