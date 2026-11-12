# ADR-0002: FastAPI y Postgres gestionado (Supabase)

- Estado: Aceptado
- Fecha: 2026-11-11
- Módulo: backend

## Contexto
El backend tiene que recibir lecturas cada pocos segundos, aplicar reglas de negocio (lotes en riesgo y merma), guardar todo con su historial y mandar eventos en tiempo real. Los datos son relacionales: cámaras tienen lotes, lotes tienen estados, alertas pertenecen a cámaras.

## Decisión
- API en **Python con FastAPI**.
- Base de datos **Postgres** gestionada en **Supabase** (plan gratis).

## Alternativas consideradas
| Opción | A favor | En contra |
|---|---|---|
| **FastAPI** | Python (lo conoce todo el equipo), asíncrono para SSE, valida los JSON solo y genera Swagger en `/docs` | — |
| Node-RED | Lo menciona el enunciado, visual | Difícil de versionar en Git y de dividir entre devs; la lógica de lotes queda escondida en nodos |
| Express (Node.js) | Muy usado | El simulador y el detector SIEM ya van en Python; tener dos lenguajes en el backend complica |
| **Postgres (Supabase)** | Relacional, gratis, sin fecha de expiración, panel para ver las tablas en la demo | Se pausa si pasa una semana sin uso |
| Postgres de Render | Todo en un mismo proveedor | La base gratis de Render expira a los 30 días |
| MongoDB Atlas | Flexible | Los datos son relacionales; las consultas de KPIs salen más simples en SQL |
| InfluxDB (series de tiempo) | Hecha para telemetría | Agrega otra base solo para lecturas; para el volumen del prototipo Postgres sobra |

## Consecuencias
- Swagger en `/docs` sirve como demo del backend y para que el dashboard pruebe sin esperar.
- Hay que manejar migraciones de la base (Alembic o scripts SQL en `backend/app/db/`).
- La conexión a Supabase va por variable de entorno, nunca en el código.
