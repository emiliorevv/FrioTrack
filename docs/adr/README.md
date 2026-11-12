# ADRs (Architecture Decision Records)

Cada archivo documenta una decisión de arquitectura: el contexto, lo que decidimos, qué otras opciones vimos y qué consecuencias tiene. Un ADR aceptado no se edita; si cambia la decisión se escribe uno nuevo que lo reemplaza y el viejo se marca como "Reemplazado por ADR-NNNN".

Plantilla: [0000-plantilla.md](0000-plantilla.md).

| ADR | Decisión | Estado |
|---|---|---|
| [0001](0001-paas-render.md) | PaaS (Render) en lugar de IaaS | Aceptado |
| [0002](0002-fastapi-postgres.md) | FastAPI y Postgres gestionado (Supabase) | Aceptado |
| [0003](0003-simulador-http.md) | Telemetría por HTTPS con token en lugar de MQTT | Aceptado |
| [0004](0004-tiempo-real-sse.md) | Tiempo real con Server-Sent Events | Aceptado |
| [0005](0005-dashboard-web-responsivo.md) | Dashboard web responsivo en lugar de app nativa | Aceptado |
| [0006](0006-idmz-zero-trust.md) | Segmentación IDMZ y Zero Trust | Aceptado |
| [0007](0007-reglas-siem-sigma.md) | Reglas SIEM en formato Sigma | Aceptado |
| [0008](0008-notificaciones-sms.md) | Alertas por SMS con Twilio | Aceptado |
| [0009](0009-cron-cloudflare-worker.md) | Flujo continuo con Cloudflare Worker | Aceptado |
