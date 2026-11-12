# Cloudflare Worker (cron)

Parte del módulo de backend. Cada minuto llama a `POST /api/simulador/tick` con el token del cron para que siempre haya datos y Render no se duerma. Decisión en [ADR-0009](../docs/adr/0009-cron-cloudflare-worker.md).

Se despliega con `wrangler deploy`. El token y la URL van como secretos del Worker, no en el código.
