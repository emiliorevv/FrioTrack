# Módulo 1 — Backend y Conectividad Cloud

Temas 3.3 y 4.3. Responsable: _por definir_.

Contiene el simulador de sensores, la API FastAPI con la lógica que emula el ERP/MES, y el Cloudflare Worker que mantiene el flujo continuo. Todo lo que expone está en [docs/contrato-api.md](../docs/contrato-api.md).

## Tareas
- [ ] Esqueleto de FastAPI con `/api/health` desplegado en Render.
- [ ] Tablas en Supabase según [docs/modelo-datos.md](../docs/modelo-datos.md), con los datos semilla que ahí se listan.
- [ ] `ESCALA_TIEMPO` en las reglas y `GET /api/health` — ver [docs/modo-demo.md](../docs/modo-demo.md).
- [ ] Rechazar con `403` las IPs de `ips_bloqueadas`.
- [ ] `POST /api/telemetria` con token por sensor.
- [ ] Reglas de negocio en `app/erp/`: estado de cámara, lotes en riesgo, merma, alerta de puerta.
- [ ] Endpoints de consulta: cámaras, lecturas, lotes, alertas, KPIs.
- [ ] `GET /api/stream` (SSE) — ver ADR-0004.
- [ ] Login con JWT y roles.
- [ ] SMS con Twilio en segundo plano — ver ADR-0008.
- [ ] Middleware que escribe el log de acceso en el formato del contrato.
- [ ] Simulador con escenarios `normal`, `puerta_abierta`, `falla_compresor` y `recuperar` (ver modo-demo.md).
- [ ] `POST /api/simulador/tick` y el Cloudflare Worker en `../cloudflare-cron/` — ver ADR-0009.
- [ ] Pruebas con `pytest` de las reglas de negocio.

## Variables de entorno
Ver `.env.example` (se crea con el esqueleto). Nunca subir `.env`.

## Cómo correr en local

Desde `backend/`:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # runtime + pytest y ruff
cp .env.example .env   # pega aquí la URI de Supabase, ver abajo
.venv/bin/uvicorn app.main:app --reload
```

En producción solo se instalan las dependencias de runtime:

```bash
pip install -r requirements.txt
```

La API queda en <http://localhost:8000> y `GET /api/health` responde
`{"ok": true, "escala_tiempo": 1}` (o el valor de `ESCALA_TIEMPO`).

Pruebas y lint, desde `backend/`:

```bash
.venv/bin/ruff check .
.venv/bin/pytest -q
```

Las pruebas no se conectan a ninguna base ni a la red: usan metadatos de
SQLAlchemy y una sesión falsa.

## Base de datos (Supabase)

El runtime habla directo con el Postgres de Supabase; no hay base local.

1. Crea el proyecto en <https://supabase.com>.
2. En **Project Settings → Database** copia la URI **Session Pooler** y pégala en
   `backend/.env`. SQLAlchemy necesita el driver `psycopg`, así que el esquema de la URL
   debe ser `postgresql+psycopg://`:

   ```bash
   DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
   ```

3. Desde `backend/`, crea las tablas y carga los datos semilla:

   ```bash
   .venv/bin/python -m app.db.init_db
   ```

   Es idempotente: si la base ya tiene cámaras, no vuelve a insertar nada.

Si `DATABASE_URL` falta o está vacía, `crear_engine()` falla con un `RuntimeError` que
explica cómo crear `backend/.env`. La aplicación no se conecta a la base al importarse.

