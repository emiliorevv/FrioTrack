# Despliegue de FríoTrack

Guía para llevar el prototipo a la nube con los planes gratuitos: API en **Render**, base de datos en **Supabase**, dashboard en **Vercel** y el flujo continuo en un **Cloudflare Worker**.

> Todos los valores entre `<...>` son marcadores: sustitúyelos por los reales. Ningún secreto va en el repo; viven en el panel de cada proveedor o como secretos de Wrangler.

## Orden recomendado

1. Supabase (base y seed).
2. Render (API).
3. Vercel (dashboard).
4. Ajustar CORS y `DASHBOARD_URL` en Render con la URL final del dashboard.
5. Cloudflare Worker (cron).
6. Smoke test y revisión de logs.

## Cuentas necesarias

- **GitHub** con acceso al repo (Render y Vercel despliegan desde ahí).
- **Supabase**, **Render**, **Vercel** y **Cloudflare**. Los cuatro tienen plan gratuito.
- **Twilio** es opcional: sin credenciales el canal simulado sigue funcionando.

## 1. Supabase

1. Crea un proyecto en <https://supabase.com> y guarda la contraseña de la base.
2. En **Project Settings → Database** copia la cadena **Session Pooler** (puerto `5432`). SQLAlchemy necesita el driver `psycopg`, así que cambia el esquema a `postgresql+psycopg://`:

   ```text
   postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
   ```

   Si la contraseña tiene caracteres especiales (`@`, `#`, `%`…), codifícalos con porcentaje o usa una contraseña alfanumérica. No uses la conexión directa: el plan gratuito no siempre la expone desde fuera.

3. Desde tu máquina, con `backend/.env` creado a partir de `backend/.env.example`, define al menos `DATABASE_URL`, `SEED_PASSWORD` y `SENSOR_TOKENS`. Después, desde `backend/`, crea las tablas y carga el seed:

   ```bash
   cd backend
   python3 -m venv .venv
   .venv/bin/pip install -r requirements-dev.txt
   .venv/bin/python -m app.db.init_db
   ```

   El comando es idempotente: si la base ya tiene cámaras, no inserta nada. `SEED_PASSWORD` será la contraseña de los usuarios `jefe` y `gerente`, así que debe ser la misma que configures en Render.

4. Verifica en el **SQL Editor** de Supabase:

   ```sql
   select count(*) from camaras;              -- 5
   select usuario, rol from usuarios;         -- jefe / gerente
   select count(*) from lotes;                -- 2 o 3 por cámara
   select id, camara_id from sensores;        -- un sensor por cámara
   ```

## 2. Render (API)

### Con el blueprint

El repo incluye [`render.yaml`](../render.yaml). En Render: **New → Blueprint**, conecta el repo y aplica el blueprint `friotrack-api`. Al crearlo, Render pide los valores de las variables marcadas con `sync: false`.

### Manual

Si prefieres crearlo a mano: **New → Web Service**, conecta el repo y usa:

| Campo | Valor |
|---|---|
| Runtime | Python |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |
| Plan | Free |

### Variables de entorno

| Variable | Valor |
|---|---|
| `ENTORNO` | `produccion` |
| `ESCALA_TIEMPO` | `30` (modo demo; `1` para operación real) |
| `AUTH_REQUERIDA` | `0` (ver sección de auth) |
| `DATABASE_URL` | cadena Session Pooler con `postgresql+psycopg://` |
| `JWT_SECRET` | cadena aleatoria de 32+ caracteres (`openssl rand -hex 32`) |
| `CRON_TOKEN` | cadena aleatoria; el mismo valor va en el Worker |
| `SENSOR_TOKENS` | JSON con un token por sensor, p. ej. `{"S-PES-01":"<token>","S-CAR-01":"<token>","S-LAC-01":"<token>","S-VER-01":"<token>","S-CON-01":"<token>"}` |
| `SEED_PASSWORD` | la misma que usaste al correr `app.db.init_db` |
| `CORS_ORIGINS` | `https://<dashboard>.vercel.app` (sin slash final; varios orígenes separados por comas) |
| `DASHBOARD_URL` | `https://<dashboard>.vercel.app` (para los enlaces de las notificaciones) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `TELEFONO_JEFE` | opcionales; ver sección de Twilio |

En el primer despliegue puedes dejar `CORS_ORIGINS` vacío (la API cae en `*`) y ajustarlo cuando Vercel te dé la URL final. No lo dejes abierto para la demo: si el dashboard tiene dominio propio, agrégalo también.

En producción la API **no arranca** si falta o es débil alguno de estos valores: `JWT_SECRET` (mínimo 32 caracteres), `CRON_TOKEN`, `SEED_PASSWORD` distinta de la de demo y un token no vacío por cada sensor. Render define `RENDER=true`, así que la validación también aplica si `ENTORNO` se queda mal. Si el deploy falla, revisa **Logs**: el mensaje dice exactamente qué variable corregir.

### Health check

Render consulta `GET /api/health` y debe responder:

```json
{ "ok": true, "escala_tiempo": 30 }
```

La URL base de la API queda como `https://<api>.onrender.com` y sus endpoints cuelgan de `/api`. La documentación interactiva está en `https://<api>.onrender.com/docs`.

## 3. Vercel (dashboard)

1. **Add New → Project**, importa el repo y elige el directorio raíz `dashboard`.
2. Framework preset: **Vite**. Build Command: `npm run build`. Output Directory: `dist`. El `vercel.json` del módulo ya reescribe todas las rutas a `index.html`, así que no hay que configurar rewrites a mano.
3. En **Settings → Environment Variables**, agrega para Production (y Preview si la usas):

   ```text
   VITE_API_URL=https://<api>.onrender.com/api
   ```

   Vite incrusta la variable en el build: si la cambias, vuelve a desplegar.
4. Despliega y anota la URL (`https://<dashboard>.vercel.app`). Un dominio propio es opcional; si lo agregas, inclúyelo en `CORS_ORIGINS` y `DASHBOARD_URL`.
5. De vuelta en Render, actualiza `CORS_ORIGINS` y `DASHBOARD_URL` con esa URL. Render reinicia el servicio al guardar.

Para probar el build en local:

```bash
cd dashboard
npm ci
npm run build
npm run preview
```

## 4. Cloudflare Worker (cron)

El Worker de `cloudflare-cron/` llama cada minuto a `POST /api/simulador/tick`. El cron está declarado en `wrangler.toml` (`* * * * *`); no hay que tocarlo ni agregar variables al archivo: la URL y el token son secretos del Worker.

```bash
cd cloudflare-cron
npx wrangler login
npx wrangler secret put API_URL      # https://<api>.onrender.com/api
npx wrangler secret put CRON_TOKEN   # el mismo CRON_TOKEN de Render
npx wrangler deploy
```

Para ver cada ejecución y sus errores:

```bash
npx wrangler tail
```

Notas:

- `API_URL` incluye `/api` y no debe terminar en slash (el Worker lo recorta de todas formas).
- Con `ESCALA_TIEMPO=30` cada tick genera lecturas normales por cámara; con `ESCALA_TIEMPO=1` solo mantiene despierta la API y responde `{ "lecturas": 0, "saltadas": [] }`.
- El Worker espera hasta 90 s la respuesta para tolerar el cold start de Render.
- El plan Free de Cloudflare incluye 100,000 solicitudes al día; este cron consume 1,440 (1.44 %).

## 5. Autenticación

En `main`, el flag `AUTH_REQUERIDA` todavía no existe en `app/config.py`; lo define el PR de auth. El blueprint lo deja en `0` para no bloquear el despliegue ni dejar fuera al dashboard antes de que exista el login.

Cuando el login del dashboard esté desplegado y probado:

1. Cambia `AUTH_REQUERIDA=1` en Render.
2. Confirma que `JWT_SECRET` es propio, aleatorio y de 32 caracteres o más (no lo rotes sin avisar: invalida los JWT vigentes).
3. El dashboard debe mandar `Authorization: Bearer <jwt>` en las llamadas REST.
4. El stream se consume como `GET /api/stream?token=<jwt>`: `EventSource` no permite cabeceras, por eso el token va en la URL. No lo pegues en logs ni en capturas.

`GET /api/health` y `/docs` quedan fuera del flag para poder diagnosticar el servicio. Si activas la auth antes que el dashboard, las pantallas responderán `401` hasta que el login esté listo.

## 6. Twilio (opcional)

El código de `main` usa el **canal simulado**: la notificación se publica por SSE en el dashboard y no sale a la red. Las variables `TWILIO_*` y `TELEFONO_JEFE` se pueden dejar vacías; el canal simulado sigue funcionando y la columna `sms_enviados` de `alertas` queda en `0`. Si más adelante se conecta el notificador real, las credenciales ya estarán en Render.

## 7. Smoke test

Con las URLs reales:

```bash
API=https://<api>.onrender.com
DASH=https://<dashboard>.vercel.app

# 1. Salud (despierta Render; la primera respuesta puede tardar ~1 min)
curl -s "$API/api/health"

# 2. Swagger
open "$API/docs"

# 3. Tick del cron con el token real (no lo pegues en el historial compartido)
curl -s -X POST "$API/api/simulador/tick" \
  -H "Authorization: Bearer $CRON_TOKEN"

# 4. Stream SSE (corta con Ctrl+C)
curl -N "$API/api/stream"

# 5. Dashboard
open "$DASH"
```

Después revisa:

- En Supabase, que las peticiones se registren:

  ```sql
  select ts, ip_origen, metodo, ruta, status, credencial
  from logs_acceso
  order by id desc
  limit 10;
  ```

- Que el cron esté generando lecturas (con `ESCALA_TIEMPO=30`):

  ```sql
  select sensor_id, count(*)
  from lecturas
  where recibida_en > now() - interval '5 minutes'
  group by sensor_id;
  ```

  Debe aparecer `SIM-CRON` mientras el simulador local no esté tapando las cámaras.

- En Render → **Logs**, que no haya errores de configuración ni de conexión a la base.
- En Vercel, que el dashboard cargue KPIs y reciba eventos sin errores de CORS en la consola del navegador.

## 8. Límites de los planes gratuitos

- **Render Free**: el servicio se duerme tras 15 minutos sin tráfico y el primer request después de eso tarda hasta ~1 minuto (cold start). El cron cada minuto lo mantiene despierto; aun así, abre la API 30 minutos antes de la exposición. Free no incluye workers en segundo plano: el detector SIEM se corre a mano o desde otra máquina con acceso a la base.
- **Cloudflare Workers Free**: 100,000 solicitudes al día; el cron usa 1,440. Al agotar el límite las ejecuciones fallan hasta el reinicio del contador.
- **Supabase Free**: el proyecto puede pausarse por inactividad; si el dashboard deja de responder, revisa el panel y reactívalo.
- **SSE**: la API acepta hasta 50 conexiones simultáneas (`MAX_CONEXIONES_STREAM`); al llenarse responde `503`. El dashboard reintenta con backoff.

## 9. Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| Render no arranca y el log habla de configuración insegura | Falta `JWT_SECRET`, `CRON_TOKEN`, `SEED_PASSWORD` o `SENSOR_TOKENS` | Corrige la variable y redeploy |
| `500` al consultar la API | `DATABASE_URL` mal formada o sin `postgresql+psycopg://` | Copia de nuevo la Session Pooler y codifica la contraseña |
| El dashboard muestra errores de CORS | `CORS_ORIGINS` no coincide con el origen exacto | Usa el origen sin slash final y redeploy |
| El cron responde `401` | `CRON_TOKEN` distinto entre Render y el Worker | Vuelve a hacer `wrangler secret put CRON_TOKEN` |
| El dashboard no se actualiza en vivo | `VITE_API_URL` mal o auth activa sin `?token=` | Revisa el build de Vercel y la consola del navegador |
| Cambié una variable de Vercel y no pasa nada | Vite la incrusta en el build | Redeploy del dashboard |

## Checklist de despliegue

- [ ] Proyecto de Supabase creado y cadena Session Pooler anotada.
- [ ] `python -m app.db.init_db` ejecutado; 5 cámaras, sensores, lotes y 2 usuarios verificados.
- [ ] Servicio `friotrack-api` en Render con todas las variables y `/api/health` en verde.
- [ ] `AUTH_REQUERIDA=0` documentado y pendiente de activar con el login.
- [ ] Dashboard en Vercel con `VITE_API_URL` apuntando a Render.
- [ ] `CORS_ORIGINS` y `DASHBOARD_URL` con la URL final de Vercel.
- [ ] Worker desplegado con `API_URL` y `CRON_TOKEN`; `wrangler tail` muestra ticks correctos.
- [ ] Smoke test completo: salud, `/docs`, dashboard, tick, SSE y `logs_acceso`.
- [ ] Credenciales fuera del repo y del historial de comandos compartido.
