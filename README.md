# FríoTrack — Monitoreo de cadena de frío 4.0

Prototipo Alfa del Desafío Data-Driven 4.0 (4ta Revolución Industrial, segundo parcial).

FríoTrack monitorea en tiempo real las cámaras frigoríficas y el congelador de la cocina de un restaurante. Sensores simulados mandan temperatura, humedad y estado de puerta a un backend en la nube. El backend cruza esas lecturas con el inventario (emulando un ERP), detecta cuando un lote de producto queda en riesgo y manda un SMS al celular del jefe de cocina antes de que se pierda.

## El problema en una frase

Hoy la temperatura de las cámaras se revisa a mano con una hoja en la puerta, dos o tres veces por turno. Si una puerta queda abierta o un compresor falla de noche, nadie se entera hasta la mañana siguiente, y el producto se tira sin saber cuánto se perdió ni por qué. El detalle está en [docs/01-problema.md](docs/01-problema.md).

## Arquitectura

Es una **arquitectura IoT en tres capas** (borde, plataforma y aplicación), con la red segmentada según el **modelo Purdue / ISA-95** (la IDMZ es su nivel 3.5). El backend es un **monolito modular** que expone una API REST y empuja eventos al dashboard (**orientado a eventos**, publicación/suscripción).

```
 ZONA OT (cocina / almacén)          IDMZ                     ZONA IT / NUBE
┌──────────────────────────┐   ┌──────────────┐   ┌──────────────────────────────────┐
│ Sensores simulados       │   │ Gateway con  │   │ API FastAPI (Render, PaaS)       │
│ (temp, humedad, puerta)  │──▶│ TLS + token  │──▶│  - ingesta de telemetría         │
│ simulator/               │   │ por sensor   │   │  - lógica ERP: lotes, mermas     │
└──────────────────────────┘   └──────────────┘   │  - alertas y SMS (Twilio)        │
                                                  │  - stream en tiempo real (SSE)   │
                                                  └───────────────┬──────────────────┘
                                                                  │
                                         ┌────────────────────────┼─────────────────┐
                                         ▼                        ▼                 ▼
                                 Postgres gestionado      Dashboard web       Logs de acceso
                                 (Supabase)               responsivo          → reglas SIEM
                                                          (celular)           security/
```

| Pieza | Tecnología | Dónde corre |
|---|---|---|
| Simulador de sensores | Python | Local, en la laptop que hace de gateway del restaurante (ahí se provocan las fallas en la demo) |
| Flujo continuo | Cloudflare Worker con Cron Trigger (plan gratis) | Cada minuto llama a `POST /api/simulador/tick`, que genera una lectura por cámara. Así siempre hay datos y Render no se duerme |
| API y lógica ERP/MES | Python + FastAPI | Render Web Service (PaaS) |
| Base de datos | Postgres | Supabase |
| Dashboard | React + Vite, responsivo | Vercel |
| Tiempo real | Server-Sent Events desde la API | — |
| Notificaciones al celular | SMS con Twilio (cuenta de prueba) | API → celular del jefe de cocina |
| Seguridad | Diagrama IDMZ + reglas SIEM en formato Sigma | `security/` |

Cada decisión tiene su ADR en [docs/adr/](docs/adr/).

## Módulos y responsables

El repo está dividido para que cada módulo lo trabaje una persona distinta sin pisarse. Los módulos solo se comunican a través del contrato de la API ([docs/contrato-api.md](docs/contrato-api.md)); si alguien necesita cambiarlo, lo hace en un PR aparte que revisan los dueños de los dos módulos afectados.

| Módulo | Carpeta | Tema | Responsable | Entregable |
|---|---|---|---|---|
| 1. Backend y Conectividad Cloud | `backend/` | 3.3 y 4.3 | _por definir_ | Simulador, API, lógica ERP, despliegue en Render y Supabase |
| 2. Ciberseguridad IT/OT y SOC | `security/` | 3.5 | _por definir_ | Diagrama IDMZ / Zero Trust, regla SIEM, script que la evalúa sobre los logs |
| 3. Dashboard e Informática Móvil | `dashboard/` | 3.4 | _por definir_ | Panel responsivo con KPIs en tiempo real, desplegado en Vercel |
| 4. Retos y Visión de Negocio | `docs/` | 3.6 y 4.4 | Todo el equipo | Barreras legacy y culturales, valor conectado, reporte PDF |

## Estructura del repo

```
.
├── backend/
│   ├── simulator/        # sensores simulados y escenarios de falla
│   ├── app/              # API FastAPI
│   │   ├── routers/      # telemetria, camaras, lotes, alertas, stream
│   │   ├── erp/          # reglas de negocio: lotes en riesgo, mermas
│   │   └── db/           # modelos y migraciones
│   ├── tests/
│   └── README.md
├── dashboard/
│   ├── src/
│   └── README.md
├── security/
│   ├── diagramas/        # IDMZ y Zero Trust (draw.io + PNG exportado)
│   ├── siem/             # reglas en formato Sigma
│   ├── detector/         # script que aplica la regla a los logs de la API
│   └── README.md
├── docs/
│   ├── 01-problema.md
│   ├── 02-barreras-y-valor.md
│   ├── contrato-api.md
│   ├── adr/
│   └── reporte/          # fuente y PDF final del reporte técnico
├── cloudflare-cron/      # Worker que llama a /api/simulador/tick cada minuto
├── .github/
│   └── pull_request_template.md
└── README.md
```

## Cámaras e inventario

El restaurante tiene cinco equipos de frío. Cada uno guarda un tipo de producto y por eso tiene su propio rango y sus propios tiempos: el pescado se echa a perder mucho más rápido que la verdura. Los rangos siguen la NOM-251-SSA1-2009 (refrigerados a 4 °C o menos, congelados a −18 °C o menos).

| Cámara | Productos | Rango | En riesgo después de | Merma después de |
|---|---|---|---|---|
| Pescados y mariscos | Pescado fresco, camarón, pulpo | 0 a 2 °C | 10 min fuera de rango | 1 h |
| Carnes y aves | Res, cerdo, pollo | 0 a 4 °C | 15 min | 2 h |
| Lácteos | Leche, crema, quesos, mantequilla | 1 a 4 °C | 20 min | 3 h |
| Verduras y frutas | Lechuga, hierbas, cítricos, frutos rojos | 4 a 8 °C | 30 min | 4 h |
| Congelador | Carnes congeladas, helado, papas | −22 a −18 °C | 20 min | 2 h |

## Lógica de negocio que emula el ERP/MES

1. Cada lote de inventario (producto, cantidad, costo y caducidad) está asignado a una cámara.
2. Si una cámara sale de su rango más del tiempo de **en riesgo**, se abre una alerta, sus lotes pasan a **en riesgo** y llega un SMS al jefe de cocina.
3. Si sigue fuera de rango más del tiempo de **merma**, los lotes pasan a **merma** y se registra la pérdida en pesos en el inventario.
4. Una puerta abierta más de **5 minutos** genera alerta aunque la temperatura siga en rango.

Los rangos y tiempos se configuran por cámara en la base de datos. Para la demo, la variable `ESCALA_TIEMPO` acelera los tiempos (ver [modo-demo.md](docs/modo-demo.md)). Las tablas están en [modelo-datos.md](docs/modelo-datos.md).

## Tiempo real y notificaciones

- **Dashboard en vivo (SSE):** el dashboard abre una conexión a `GET /api/stream` que se queda abierta. Cada vez que la API recibe una lectura o abre una alerta, la manda por esa conexión y la pantalla se actualiza sola, sin recargar. Si se cae la conexión, el navegador se reconecta automáticamente.
- **SMS (Twilio):** cuando se abre una alerta, la API le manda un SMS al jefe de cocina con la cámara, la temperatura y el valor del producto en riesgo, más el link al dashboard. Para no llenarlo de mensajes, se manda un SMS al abrir la alerta y otro si pasa a merma, no uno por lectura. La cuenta de prueba de Twilio da crédito gratis y solo manda a números verificados, que para la demo basta (se verifican los celulares del equipo).

## KPIs del dashboard

- Temperatura actual y estado por cámara (en rango, en alerta, crítica).
- Porcentaje del tiempo en rango en las últimas 24 horas.
- Alertas activas y tiempo de respuesta.
- Lotes en riesgo por cámara y valor del producto en riesgo, en pesos.
- Mermas del día y del mes.

## Cómo correrlo en local

> Se completa cuando cada módulo tenga su primera versión.

```bash
# backend
cd backend && cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload

# simulador (en otra terminal)
python -m simulator --escenario normal      # o: puerta_abierta, falla_compresor

# dashboard
cd dashboard && cp .env.example .env
npm install && npm run dev
```

## Despliegue

| Servicio | URL |
|---|---|
| API | _pendiente_ |
| Dashboard | _pendiente_ |
| Documentación de la API (Swagger) | _pendiente_ (`/docs` de la API) |

## Prácticas del equipo

### Ramas y PRs
- `main` está protegida: nadie hace push directo, todo entra por PR.
- Una rama por tarea con el prefijo del módulo: `backend/ingesta-telemetria`, `dashboard/tarjeta-camara`, `security/regla-puerta`, `docs/adr-0003`.
- Cada PR necesita la aprobación de al menos una persona del equipo. Los cambios en `docs/contrato-api.md` necesitan la aprobación del dueño del backend y del dashboard.
- Los PRs son chicos: una tarea por PR. Si pasa de unas 400 líneas, se divide.

### Commits
Usamos [Conventional Commits](https://www.conventionalcommits.org/es/) con el módulo como scope:

```
feat(backend): endpoint de ingesta de telemetría
fix(dashboard): color de la tarjeta en estado crítico
docs(adr): ADR-0004 tiempo real con SSE
```

### Issues y tablero
- Cada tarea es un issue con la etiqueta de su módulo (`backend`, `dashboard`, `security`, `docs`).
- El tablero de GitHub Projects tiene las columnas Pendiente, En curso, En revisión y Hecho.
- El PR cierra su issue con `Closes #N`.

### Código
- Python: formato y lint con `ruff`, tipos con type hints, pruebas con `pytest`.
- Dashboard: `eslint` y `prettier`.
- Nada de secretos en el repo: las credenciales van en `.env` (ignorado por git) y en las variables de entorno de Render y Vercel. Cada módulo tiene un `.env.example`.

### Decisiones (ADRs)
Toda decisión de arquitectura se escribe como ADR en `docs/adr/NNNN-titulo.md` con el formato: contexto, decisión, alternativas consideradas y consecuencias. Un ADR aceptado no se edita; si cambia la decisión se escribe uno nuevo que lo reemplaza.

### Definición de terminado
Una tarea está terminada cuando:
1. Está mergeada en `main`.
2. Corre desplegada, no solo en local.
3. Si cambió el contrato de la API, `docs/contrato-api.md` está actualizado.
4. Si fue una decisión de arquitectura, tiene su ADR.

## Documentación

| Documento | Contenido |
|---|---|
| [01-problema.md](docs/01-problema.md) | El problema, a quién le duele y cuánto cuesta |
| [02-barreras-y-valor.md](docs/02-barreras-y-valor.md) | Retos legacy y culturales, y el valor conectado |
| [contrato-api.md](docs/contrato-api.md) | Endpoints, formatos y eventos en tiempo real |
| [modelo-datos.md](docs/modelo-datos.md) | Tablas y columnas de la base, compartidas por backend y seguridad |
| [modo-demo.md](docs/modo-demo.md) | Escala de tiempo para la demo, escenarios del simulador y guion de 6 minutos |
| [ADR-0001](docs/adr/0001-paas-render.md) | PaaS (Render) en lugar de IaaS |
| [ADR-0002](docs/adr/0002-fastapi-postgres.md) | FastAPI y Postgres gestionado |
| [ADR-0003](docs/adr/0003-simulador-http.md) | Telemetría por HTTP con token en lugar de MQTT |
| [ADR-0004](docs/adr/0004-tiempo-real-sse.md) | Tiempo real con SSE |
| [ADR-0005](docs/adr/0005-dashboard-web-responsivo.md) | Dashboard web responsivo en lugar de app nativa |
| [ADR-0006](docs/adr/0006-idmz-zero-trust.md) | Segmentación IDMZ y Zero Trust |
| [ADR-0007](docs/adr/0007-reglas-siem-sigma.md) | Reglas SIEM en formato Sigma |
| [ADR-0008](docs/adr/0008-notificaciones-sms.md) | Alertas por SMS (Twilio) en lugar de app nativa, Web Push o WhatsApp |
| [ADR-0009](docs/adr/0009-cron-cloudflare-worker.md) | Flujo continuo con Cloudflare Worker en lugar de worker de Render |
| [ADR-0010](docs/adr/0010-escala-tiempo-demo.md) | Escala de tiempo para que la demo quepa en 6 minutos |

## Equipo

| Nombre | Módulo |
|---|---|
| _por definir_ | Backend y Conectividad Cloud |
| _por definir_ | Ciberseguridad IT/OT y SOC |
| _por definir_ | Dashboard e Informática Móvil |
