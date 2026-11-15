# Migraciones de base de datos (Alembic)

El esquema de Postgres se versiona con [Alembic](https://alembic.sqlalchemy.org/).
La fuente de verdad son los modelos de `backend/app/db/models.py` y las
migraciones de `backend/alembic/versions/`.

## Por qué Alembic y no `create_all`

`Base.metadata.create_all` solo crea tablas que faltan: no registra historial, no
aplica cambios de columnas ni índices sobre una base existente y no permite
revisar ni revertir lo que se ejecutó. Alembic guarda una revisión aplicada en la
tabla `alembic_version`, genera el SQL a partir del diff entre los modelos y la
base, y deja cada cambio en un archivo revisable y versionado en git.

`create_all` ya no se usa en el camino normal. `app.db.init_db` solo carga el
seed y falla con un mensaje claro si falta el esquema.

## Baseline

La revisión `0001` (`backend/alembic/versions/0001_esquema_inicial.py`) crea las
9 tablas actuales con sus FKs, índices, JSONB y columnas `BIGSERIAL`. Se generó
contra un Postgres vacío y se verificó con `alembic check` sin drift.

### Base nueva

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/python -m app.db.init_db
```

`upgrade head` crea el esquema y `init_db` inserta el seed (cámaras, lotes,
sensores y usuarios). Si `DATABASE_URL` no está en el entorno, Alembic la lee de
`backend/.env`; nunca se guarda en `alembic.ini`.

### Base existente (creada antes con `create_all`)

Si la base ya tiene las 9 tablas y datos, **no** ejecutes `upgrade head`: el
baseline intentaría crear tablas que ya existen. Marca la revisión como aplicada
una sola vez:

```bash
cd backend
DATABASE_URL='postgresql+psycopg://...' .venv/bin/alembic stamp head
DATABASE_URL='postgresql+psycopg://...' .venv/bin/alembic current   # 0001 (head)
DATABASE_URL='postgresql+psycopg://...' .venv/bin/alembic check     # sin drift
```

`stamp` no valida el esquema, solo escribe la versión. Por eso `alembic check`
es obligatorio después: si reporta diferencias, no las apliques a ciegas;
revisa si la base real se desvió de los modelos y corrige con una migración
nueva.

## Flujo para un cambio de esquema

1. Cambia los modelos en `backend/app/db/models.py`.
2. Genera la revisión contra una base local al día:

   ```bash
   cd backend
   .venv/bin/alembic revision --autogenerate -m "describe el cambio"
   ```

3. Revisa el archivo nuevo en `backend/alembic/versions/`: nombres, tipos,
   `nullable`, índices y el `downgrade`. Autogenerate no detecta todo (renombres
   los interpreta como drop + create, por ejemplo).
4. Aplica y comprueba que no queda drift:

   ```bash
   .venv/bin/alembic upgrade head
   .venv/bin/alembic check
   ```

5. Prueba también el descenso si la migración es reversible:

   ```bash
   .venv/bin/alembic downgrade -1
   .venv/bin/alembic upgrade head
   ```

6. Commitea juntos el modelo y la migración.

Reglas:

- **Nunca edites una migración ya aplicada** en producción. Corrige con una
  revisión nueva (`alembic revision -m "corrige ..."`).
- **Nunca cambies el esquema desde el SQL Editor de Supabase.** Un `ALTER TABLE`
  manual deja la base fuera del historial y `alembic check` lo detectará como
  drift. Todo cambio va por una migración en el repo.
- `compare_server_default` está apagado a propósito: los defaults actuales son
  de Python (`default=`), no `server_default=`, y compararlos generaría ruido.

## CI

El job `backend` de `.github/workflows/ci.yml` levanta un service `postgres:16`
y, antes de pytest, ejecuta:

```bash
alembic upgrade head
alembic check
alembic downgrade base
alembic upgrade head
```

Así cada PR valida que el baseline aplica desde cero, que no hay drift entre
modelos y migraciones, y que el `downgrade` funciona. Las pruebas de pytest no
se conectan a esa base; el service es para las migraciones.

## Deploy en Render

Render Free **no** ofrece `preDeployCommand` (solo planes pagos). Por eso el
`startCommand` de `render.yaml` corre las migraciones al iniciar:

```yaml
startCommand: alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log
```

En Free hay una sola instancia, así que no hay dos procesos compitiendo por la
migración. En un plan pago conviene mover `alembic upgrade head` a
`preDeployCommand` para que falle el deploy antes de arrancar la nueva versión y
para no pagar el costo en cada cold start.

## Backups y rollback

Antes de una migración destructiva (drop de columna o tabla, cambio de tipo con
pérdida de datos):

1. Descarga un respaldo con `pg_dump` (o usa el backup/PITR del panel de
   Supabase si tu plan lo incluye) y guárdalo fuera del repo.
2. Prefiere el patrón expand/contract: agrega la columna nueva, backfill, cambia
   el código, y elimina la vieja en una migración posterior.
3. Prueba el `downgrade` en una base temporal antes del deploy.

Rollback: `alembic downgrade -1` revierte el esquema, pero **no** recupera datos
borrados por un `DROP` o un cambio de tipo. Si hubo pérdida de datos, restaura el
dump o el point-in-time; el downgrade solo devuelve la forma del esquema.

## Probar migraciones en local sin Supabase

Cualquier Postgres sirve. Por ejemplo, con Homebrew:

```bash
TMP=$(mktemp -d)
initdb -D "$TMP/data" -U postgres --auth=trust
pg_ctl -D "$TMP/data" -o "-p 55432 -k $TMP -h 127.0.0.1" -l "$TMP/log" start
createdb -h 127.0.0.1 -p 55432 -U postgres friotrack

cd backend
export DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55432/friotrack'
export ENTORNO=local
.venv/bin/alembic upgrade head
.venv/bin/alembic check
.venv/bin/alembic downgrade base
.venv/bin/alembic upgrade head

pg_ctl -D "$TMP/data" stop
```

No corras `alembic stamp` contra Supabase sin revisar antes el PR: la versión
marcada debe corresponder al esquema real.
