# Módulo 1 — Backend y Conectividad Cloud

Temas 3.3 y 4.3. Responsable: _por definir_.

Contiene el simulador de sensores, la API FastAPI con la lógica que emula el ERP/MES, y el Cloudflare Worker que mantiene el flujo continuo. Todo lo que expone está en [docs/contrato-api.md](../docs/contrato-api.md).

## Tareas
- [ ] Esqueleto de FastAPI con `/api/health` desplegado en Render.
- [ ] Tablas en Supabase: `camaras`, `lotes`, `lecturas`, `alertas`, `sensores`, `usuarios`, `logs_acceso`, con datos semilla (las 5 cámaras del README y unos lotes por cámara).
- [ ] `POST /api/telemetria` con token por sensor.
- [ ] Reglas de negocio en `app/erp/`: estado de cámara, lotes en riesgo, merma, alerta de puerta.
- [ ] Endpoints de consulta: cámaras, lecturas, lotes, alertas, KPIs.
- [ ] `GET /api/stream` (SSE) — ver ADR-0004.
- [ ] Login con JWT y roles.
- [ ] SMS con Twilio en segundo plano — ver ADR-0008.
- [ ] Middleware que escribe el log de acceso en el formato del contrato.
- [ ] Simulador con escenarios `normal`, `puerta_abierta` y `falla_compresor`.
- [ ] `POST /api/simulador/tick` y el Cloudflare Worker en `../cloudflare-cron/` — ver ADR-0009.
- [ ] Pruebas con `pytest` de las reglas de negocio.

## Variables de entorno
Ver `.env.example` (se crea con el esqueleto). Nunca subir `.env`.
