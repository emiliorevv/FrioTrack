# Cloudflare Worker (cron)

Parte del módulo de backend. Cada minuto llama a `POST /api/simulador/tick` con el token del cron para que siempre haya datos y Render no se duerma. Decisión en [ADR-0009](../docs/adr/0009-cron-cloudflare-worker.md).

El token y la URL van como secretos del Worker, no en el código. `src/index.js` solo hace el `POST` y reporta el resultado en los logs.

## Uso local

```bash
cd cloudflare-cron
cp .dev.vars.example .dev.vars   # ajusta API_URL y CRON_TOKEN; .dev.vars no se sube
wrangler dev --test-scheduled
# en otra terminal, dispara el cron una vez:
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"
```

## Despliegue

Ya con la cuenta autenticada (`wrangler login`):

```bash
cd cloudflare-cron
wrangler secret put API_URL     # https://<servicio>.onrender.com/api
wrangler secret put CRON_TOKEN  # el mismo CRON_TOKEN del backend
wrangler deploy
```

Para ver cada ejecución (y los errores del tick) mientras corre:

```bash
wrangler tail
```

El plan Free de Cloudflare incluye **100,000 solicitudes al día**; este cron consume 1,440 (1.44 %). Al agotar el límite las solicitudes fallan hasta el reinicio del contador, y en Free no hay cobro por excedente.
