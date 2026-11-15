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

3. **Genera credenciales nuevas antes de sembrar.** No copies `backend/.env.example` cambiando solo `DATABASE_URL`: ese archivo trae `ENTORNO=local`, así que el seed no ejecuta las validaciones de producción y acepta los valores de demo sin avisar. Además, el seed guarda en `sensores.token_hash` el SHA-256 de los tokens que tenga en ese momento, y la API autentica la telemetría contra ese hash, **no** contra el `SENSOR_TOKENS` que configures después en Render. Si siembras con los tokens de ejemplo (`token-pes-ejemplo`, etc.), quedan publicados en el repo y producción los aceptaría.

   Genera cinco tokens y una contraseña:

   ```bash
   cd backend
   python3 -c 'import json, secrets; print(json.dumps({s: secrets.token_hex(16) for s in ("S-PES-01", "S-CAR-01", "S-LAC-01", "S-VER-01", "S-CON-01")}))'
   openssl rand -hex 16   # SEED_PASSWORD
   ```

   Copia el JSON que imprime el primer comando y la contraseña en `backend/.env` (archivo ignorado por git):

   ```dotenv
   DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
   SENSOR_TOKENS='{"S-PES-01":"<token-1>","S-CAR-01":"<token-2>","S-LAC-01":"<token-3>","S-VER-01":"<token-4>","S-CON-01":"<token-5>"}'
   SEED_PASSWORD='<contraseña-nueva>'
   ```

   Usa **exactamente el mismo** JSON de `SENSOR_TOKENS` en el seed y en Render (en Render se pega sin las comillas simples exteriores). `SEED_PASSWORD` también debe coincidir con la de Render.

4. Crea el esquema y carga el seed, desde `backend/`:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements-dev.txt
   .venv/bin/python -m app.db.migrar
   .venv/bin/python -m app.db.init_db
   ```

   `python -m app.db.migrar` aplica el baseline `0001` y deja el historial en la
   tabla `alembic_version`; el detalle está en [migraciones.md](migraciones.md).
   Si la base **ya existía** con las tablas creadas por `create_all`, el
   entrypoint la marca automáticamente **solo si el esquema coincide**; si hay
   drift falla sin tocar nada (no hace falta un `stamp` manual). `init_db` solo
   carga el seed (ya no crea tablas), exige que la revisión sea head y es
   idempotente: si la base ya tiene cámaras, no inserta nada. **No rota tokens ni contraseñas**: si ya sembraste con los tokens de ejemplo en una base de prueba, recréala y vuelve a sembrar; si tiene datos que conservar, actualiza a mano `sensores.token_hash` con el SHA-256 del token nuevo y el `password_hash` de `usuarios` (puedes generarlo con `hash_password()` de `app.core.security`).

5. Verifica en el **SQL Editor** de Supabase:

   ```sql
   select count(*) from camaras;              -- 5
   select usuario, rol from usuarios;         -- jefe / gerente
   select count(*) from lotes;                -- 15 (3 por cámara)
   select id, camara_id from sensores;        -- un sensor por cámara
   ```

## 2. Render (API)

### Con el blueprint

El repo incluye [`render.yaml`](../render.yaml). En Render: **New → Blueprint**, conecta el repo y aplica el blueprint `friotrack-api`. Al crearlo, Render pide los valores de las variables marcadas con `sync: false`; esas variables quedan bajo control del panel y el blueprint **no** las pisa en las siguientes sincronizaciones. Las que llevan `value:` (por ejemplo `ESCALA_TIEMPO`) sí se toman de `render.yaml`: para cambiarlas, edita el archivo, no solo el panel. El `startCommand` corre `python -m app.db.migrar` antes de uvicorn porque Render Free no tiene `preDeployCommand`; el entrypoint verifica la revisión y no ejecuta DDL si ya está al día (ver [migraciones.md](migraciones.md)).

### Manual

Si prefieres crearlo a mano: **New → Web Service**, conecta el repo y usa:

| Campo | Valor |
|---|---|
| Runtime | Python |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python -m app.db.migrar && uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log` |
| Health Check Path | `/api/health` |
| Plan | Free |

### Variables de entorno

| Variable | Valor |
|---|---|
| `PYTHON_VERSION` | `3.13.7` (fija la misma minor que CI; evita que el default de Render cambie) |
| `ENTORNO` | `produccion` |
| `ESCALA_TIEMPO` | `30` en `render.yaml` (modo demo). Para operación real cambia ese `value` a `1` en el archivo |
| `AUTH_REQUERIDA` | `0` mientras no exista login; `1` en producción cuando el login del dashboard esté desplegado. Se captura con `sync: false` |
| `DATABASE_URL` | cadena Session Pooler con `postgresql+psycopg://` |
| `JWT_SECRET` | cadena aleatoria de 32+ caracteres (`openssl rand -hex 32`) |
| `CRON_TOKEN` | cadena aleatoria; el mismo valor va en el Worker |
| `SENSOR_TOKENS` | el JSON **exacto** que usaste al sembrar, sin las comillas simples exteriores; p. ej. `{"S-PES-01":"<token-1>","S-CAR-01":"<token-2>","S-LAC-01":"<token-3>","S-VER-01":"<token-4>","S-CON-01":"<token-5>"}` |
| `SEED_PASSWORD` | la misma que usaste al correr `app.db.init_db` |
| `CORS_ORIGINS` | `https://<dashboard>.vercel.app` (sin slash final; varios orígenes separados por comas) |
| `DASHBOARD_URL` | `https://<dashboard>.vercel.app` (para los enlaces de las notificaciones) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `TELEFONO_JEFE` | opcionales; ver sección de Twilio |

`sync: false` significa que Render pide el valor al crear el servicio y después lo administra desde **Environment**; el blueprint no lo sobrescribe. Si el equipo cambia `AUTH_REQUERIDA` de `0` a `1` en el panel, ese cambio se conserva. En cambio, `ESCALA_TIEMPO` se toma de `render.yaml`: si solo lo cambias en el panel, la siguiente sincronización del blueprint lo revierte a `30`.

En el primer despliegue puedes dejar `CORS_ORIGINS` vacío (la API cae en `*`) y ajustarlo cuando Vercel te dé la URL final. No lo dejes abierto para la demo: si el dashboard tiene dominio propio, agrégalo también.

En producción la API **no arranca** si falta o es débil alguno de estos valores: `JWT_SECRET` (mínimo 32 caracteres), `CRON_TOKEN`, `SEED_PASSWORD` distinta de la de demo y un token no vacío por cada sensor. Render define `RENDER=true`, así que la validación también aplica si `ENTORNO` se queda mal. Si el deploy falla, revisa **Logs**: el mensaje dice exactamente qué variable corregir. El `SENSOR_TOKENS` de Render solo se usa para validar el arranque (y para sembrar una base nueva); la autenticación real de los sensores compara contra el hash guardado en la base.

### Health check

Render consulta `GET /api/health` y debe responder:

```json
{ "ok": true, "escala_tiempo": 30 }
```

Mientras el PR de auth (#44) no esté mergeado, el health check pasa por `AccesoLogMiddleware`: cada chequeo puede registrar una fila en `logs_acceso` y, si la IP del checker de Render acaba en `ips_bloqueadas`, recibir `403`, con lo que Render marcaría el servicio como no sano. Cuando #44 esté mergeado, `/api/health` queda excluido del log y del bloqueo; esta guía no requiere tocar `backend/`.

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

En `main`, el flag `AUTH_REQUERIDA` todavía no existe en `app/config.py`; lo agrega el PR de auth (#44). El blueprint lo declara con `sync: false`: al crear el servicio Render pide el valor y después **no lo pisa**. Pon `0` mientras el login del dashboard no esté desplegado; en producción el valor debe ser `1` en cuanto el login esté listo. `0` solo es aceptable en desarrollo o en la transición.

Cuando el login del dashboard esté desplegado y probado:

1. Cambia `AUTH_REQUERIDA` a `1` en el panel de Render (con `sync: false` el blueprint respeta ese valor).
2. Confirma que `JWT_SECRET` es propio, aleatorio y de 32 caracteres o más (no lo rotes sin avisar: invalida los JWT vigentes).
3. El dashboard debe mandar `Authorization: Bearer <jwt>` en las llamadas REST.
4. El stream se consume como `GET /api/stream?token=<jwt>`: `EventSource` no permite cabeceras, por eso el token va en la URL. No lo pegues en logs ni en capturas.
5. El `startCommand` del blueprint ya incluye `--no-access-log`: uvicorn no escribe la URL del stream en su access log, así que el JWT del `?token=` no queda ahí. El `AccesoLogMiddleware` propio sigue registrando método, ruta **sin query string** y status, de modo que la auditoría no se pierde.

`GET /api/health` y `/docs` quedan fuera del flag para poder diagnosticar el servicio. Si activas la auth antes que el dashboard, las pantallas responderán `401` hasta que el login esté listo.

## 6. Twilio (opcional)

El código de `main` usa el **canal simulado**: la notificación se publica por SSE en el dashboard y no sale a la red. Las variables `TWILIO_*` y `TELEFONO_JEFE` se pueden dejar vacías; el canal simulado sigue funcionando y la columna `sms_enviados` de `alertas` queda en `0`. Si más adelante se conecta el notificador real, las credenciales ya estarán en Render.

## 7. Smoke test

Con las URLs reales:

```bash
API=https://<api>.onrender.com
DASH=https://<dashboard>.vercel.app

# Pega el CRON_TOKEN de Render sin mostrarlo ni dejarlo en el historial.
printf "CRON_TOKEN: "
read -rs CRON_TOKEN
echo

# 1. Salud (despierta Render; la primera respuesta puede tardar ~1 min)
curl -s "$API/api/health"

# 2. Swagger
open "$API/docs"

# 3. Tick del cron con el token capturado arriba. No lo dejes vacío:
#    "Authorization: Bearer " produce 401 y cuenta para la regla de fuerza bruta.
curl -s -X POST "$API/api/simulador/tick" \
  -H "Authorization: Bearer $CRON_TOKEN"

# 4. Stream SSE (corta con Ctrl+C)
curl -N "$API/api/stream"                  # con AUTH_REQUERIDA=0
# curl -N "$API/api/stream?token=<jwt>"    # con AUTH_REQUERIDA=1

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

- **Render Free**: **750 horas de instancia al mes por workspace**. El servicio se duerme tras 15 minutos sin tráfico y el primer request después de eso tarda hasta ~1 minuto (cold start). El cron cada minuto lo mantiene despierto 24/7, lo que consume aproximadamente 720–744 horas al mes: casi toda la cuota, sin margen para otro servicio Free en el mismo workspace. Si se agota, Render suspende los servicios antes de fin de mes. Para la demo conviene **una sola instancia Free**; si no necesitas el flujo continuo todo el mes, deja el Worker desplegado solo cerca de la exposición (mientras el cron esté activo, la API no duerme) o suspende el servicio el resto del mes. Free no incluye workers en segundo plano: el detector SIEM se corre a mano o desde otra máquina con acceso a la base (ver sección 9).
- **Cloudflare Workers Free**: 100,000 solicitudes al día; el cron usa 1,440. Al agotar el límite las ejecuciones fallan hasta el reinicio del contador.
- **Supabase Free**: el proyecto puede pausarse por inactividad; si el dashboard deja de responder, revisa el panel y reactívalo.
- **SSE**: la API acepta hasta 50 conexiones simultáneas (`MAX_CONEXIONES_STREAM`); al llenarse responde `503`. El dashboard reintenta con backoff.

## 9. Detector SIEM contra producción

El detector no corre en Render Free (no hay workers en segundo plano). Se ejecuta desde una máquina con acceso a la base, normalmente la laptop del equipo, con `ENTORNO=produccion` y `RENDER=true` para que aplique las reglas de producción:

```bash
ENTORNO=produccion RENDER=true \
  IPS_RESTAURANTE="<IP pública de salida del restaurante>" \
  PYTHONPATH=. backend/.venv/bin/python -m security.detector --once
```

La opción equivalente es `--ips-permitidas "<IP o CIDR>"`. Sin esa allowlist, el detector usa el default de loopback (`127.0.0.1,::1`), y como los accesos reales llegan a Render desde IPs públicas, la regla de token desde IP desconocida marcaría a **todos** los sensores y su acción `revocar_token` los dejaría inactivos. Usa la **IP pública de salida del restaurante** (la que ves en `logs_acceso.ip_origen`), no la IP privada de la VLAN. En producción el detector falla cerrado si la allowlist es solo loopback; `--permitir-loopback-en-produccion` existe únicamente para una demo local.

Corre primero en seco para revisar los hallazgos sin escribir alertas ni bloqueos:

```bash
ENTORNO=produccion RENDER=true \
  IPS_RESTAURANTE="<IP pública de salida del restaurante>" \
  PYTHONPATH=. backend/.venv/bin/python -m security.detector --once --dry-run
```

Todos los equipos del restaurante salen por el mismo NAT, así que una sola IP pública cubre sensores y simulador, pero también implica que bloquearla cortaría la telemetría completa. Esa limitación y la recomendación de mover el bloqueo a la IDMZ están en [el reporte de seguridad](reporte/seguridad.md#limitaciones-y-siguientes-pasos).

## 10. Problemas comunes

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
- [ ] Esquema aplicado con `python -m app.db.migrar` (base nueva o legada); `alembic current` = `0001 (head)` y `alembic check` limpio.
- [ ] `SENSOR_TOKENS` y `SEED_PASSWORD` nuevos generados; el **mismo** JSON de sensores quedó en el seed y en Render (no los de `.env.example`).
- [ ] `python -m app.db.init_db` ejecutado; 5 cámaras, 15 lotes (3 por cámara), sensores y 2 usuarios verificados. Si la base ya estaba sembrada con tokens de ejemplo, se rotaron a mano.
- [ ] Servicio `friotrack-api` en Render con `PYTHON_VERSION=3.13.7`, `--no-access-log`, todas las variables y `/api/health` en verde.
- [ ] `AUTH_REQUERIDA` capturada con `sync: false`: `0` en transición y `1` cuando el login del dashboard esté desplegado.
- [ ] Dashboard en Vercel con `VITE_API_URL` apuntando a Render.
- [ ] `CORS_ORIGINS` y `DASHBOARD_URL` con la URL final de Vercel.
- [ ] Worker desplegado con `API_URL` y `CRON_TOKEN`; `wrangler tail` muestra ticks correctos.
- [ ] Detector corrido con `--once --dry-run` e `IPS_RESTAURANTE` con la IP pública del restaurante antes de escribir alertas.
- [ ] Smoke test completo: salud, `/docs`, dashboard, tick, SSE y `logs_acceso`.
- [ ] Cuota de Render revisada: una sola instancia Free y el Worker activo solo lo necesario.
- [ ] Credenciales fuera del repo y del historial de comandos compartido.
