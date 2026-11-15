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

`create_all` ya no se usa en el camino normal. El entrypoint
`python -m app.db.migrar` verifica la revisión y aplica el esquema; `app.db.init_db`
solo carga el seed y falla si el esquema falta o está desactualizado.

## Baseline

La revisión `0001` (`backend/alembic/versions/0001_esquema_inicial.py`) crea las
9 tablas actuales con sus FKs, índices, JSONB y columnas `BIGSERIAL`. Se generó
contra un Postgres vacío y se verificó con `alembic check` sin drift.

### Base nueva

```bash
cd backend
.venv/bin/python -m app.db.migrar   # aplica el baseline 0001
.venv/bin/python -m app.db.init_db  # carga el seed
```

`app.db.migrar` crea el esquema y `init_db` inserta cámaras, lotes, sensores y
usuarios. Si `DATABASE_URL` no está en el entorno, se lee de `backend/.env`
(ruta absoluta: también funciona desde la raíz del repo); nunca se guarda en
`alembic.ini`.

### Base existente (creada antes con `create_all`)

El entrypoint detecta el caso: si no existe `alembic_version` pero sí la tabla
`camaras`, compara `Base.metadata` contra la base (`compare_type=True`) y:

- si el esquema coincide, marca `0001` como aplicada (`stamp`) sin ejecutar DDL;
- si hay diferencias, **falla sin marcar nada** con un mensaje que pide revisar
  el drift y crear una migración.

Por eso el deploy ya no depende de un `stamp` manual. `alembic stamp head` sigue
disponible para marcar una base a mano, pero úsalo solo después de comprobar el
esquema:

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
modelos y migraciones, y que el `downgrade` funciona. `ENTORNO=local` y
`DATABASE_URL` se definen solo en ese step, así que pytest sigue sin conectarse a
la base; además, el guard del baseline permite el `downgrade` porque CI corre en
local.

## Deploy en Render

Render Free **no** ofrece `preDeployCommand` (solo planes pagos). Por eso el
`startCommand` de `render.yaml` corre el entrypoint seguro al iniciar:

```yaml
startCommand: python -m app.db.migrar && uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log
```

`app.db.migrar` hace un chequeo barato primero: si `alembic_version` ya está en
head, imprime “Esquema al día” y sale sin `upgrade` ni DDL. Solo migra cuando
falta la revisión o la base está vacía, y solo marca una base legada si el
esquema coincide. Ese chequeo no llama a `validar_configuracion()`; la
validación de producción sigue ocurriendo cuando arranca `app.main`.

Tradeoff de Free: cada cold start paga importar Python/modelos y una ida y
vuelta a la base para confirmar que está al día, antes de que uvicorn pueda
servir el request que despertó la instancia. En Free hay una sola instancia, así
que no hay dos procesos compitiendo. En un plan pago conviene mover
`python -m app.db.migrar` a `preDeployCommand` para que falle el deploy antes de
arrancar la versión nueva y para no pagarlo en cada wake-up.

## Backups y rollback

Antes de una migración destructiva (drop de columna o tabla, cambio de tipo con
pérdida de datos):

1. Descarga un respaldo con `pg_dump` (o usa el backup/PITR del panel de
   Supabase si tu plan lo incluye) y guárdalo fuera del repo.
2. Prefiere el patrón expand/contract: agrega la columna nueva, backfill, cambia
   el código, y elimina la vieja en una migración posterior.
3. Prueba el `downgrade` en una base temporal antes del deploy.

Rollback: `alembic downgrade -1` revierte cambios de una migración posterior,
pero **no** recupera datos borrados por un `DROP` o un cambio de tipo. Si hubo
pérdida de datos, restaura el dump o el point-in-time; el downgrade solo
devuelve la forma del esquema.

> **Peligro con el baseline:** `alembic downgrade base` sobre `0001` borra las
> 9 tablas y todos los datos. Nunca lo uses para “revertir un deploy” en
> producción. El `downgrade()` del baseline se niega a correr si `RENDER` está
> definido o si `ENTORNO` no es `local`; solo se permite en local/CI.

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
.venv/bin/python -m app.db.migrar   # base vacía: aplica el baseline
.venv/bin/alembic check
.venv/bin/alembic downgrade base    # permitido solo con ENTORNO=local
.venv/bin/alembic upgrade head

pg_ctl -D "$TMP/data" stop
```

No corras `alembic stamp` contra Supabase sin revisar antes el PR: la versión
marcada debe corresponder al esquema real. Para una base legada, prefiere
`python -m app.db.migrar`, que solo marca si el esquema coincide.
