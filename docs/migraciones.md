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
9 tablas originales con sus FKs, índices, JSONB y columnas `BIGSERIAL`. Se generó
contra un Postgres vacío y se verificó con `alembic check` sin drift.

La revisión `0002` (`0002_restaurantes_tenant.py`) agrega `restaurantes` y
`restaurante_id` en `usuarios` y `camaras`; `lotes` y `alertas` derivan su tenant
de la cámara. Es la revisión head actual.

### Base nueva

```bash
cd backend
.venv/bin/python -m app.db.migrar   # aplica 0001 + 0002
.venv/bin/python -m app.db.init_db  # carga el seed
```

`app.db.migrar` crea el esquema y `init_db` inserta cámaras, lotes, sensores y
usuarios. Si `DATABASE_URL` no está en el entorno, se lee de `backend/.env`
(ruta absoluta: también funciona desde la raíz del repo); nunca se guarda en
`alembic.ini`.

### Base existente (creada antes con `create_all`)

El entrypoint detecta el caso: si no existe `alembic_version` pero sí la tabla
`camaras`, compara `Base.metadata` contra la base (`compare_type=True`) y:

- si el esquema coincide, marca la revisión head actual (hoy `0002`) como aplicada
  (`stamp`) sin ejecutar DDL;
- si hay diferencias, **falla sin marcar nada** con un mensaje que pide revisar
  el drift y crear una migración.

Por eso el deploy ya no depende de un `stamp` manual. `alembic stamp head` sigue
disponible para marcar una base a mano, pero úsalo solo después de comprobar el
esquema:

```bash
cd backend
DATABASE_URL='postgresql+psycopg://...' .venv/bin/alembic stamp head
DATABASE_URL='postgresql+psycopg://...' .venv/bin/alembic current   # 0002 (head actual)
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
y, antes de pytest, ejecuta el mismo entrypoint que Render:

```bash
python -m app.db.migrar      # base vacía: aplica el baseline
python -m app.db.migrar      # segunda vez: debe imprimir “Esquema al día”
alembic check
# base legada: tablas con create_all y sin alembic_version
python -m app.db.migrar      # hace stamp, no DDL
alembic current              # 0002 (head actual)
alembic check
alembic downgrade base       # permitido: el host del service es localhost
alembic upgrade head
```

Así cada PR valida el entrypoint real de producción, que el baseline aplica
desde cero, que no hay drift entre modelos y migraciones, y que el `downgrade`
funciona. `ENTORNO=local` y `DATABASE_URL` se definen solo en ese step, así que
pytest sigue sin conectarse a la base.

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

Si haces rollback de Render a un deploy que solo conoce `0001` y la base ya está
en `0002`, el entrypoint detecta que la revisión aplicada no existe en ese código,
imprime una advertencia (“La BD está en una revisión más nueva que este deploy”)
y arranca la app **sin ejecutar DDL**, en vez de fallar con “Can't locate
revision”. Un `alembic_version` sin fila pero con tablas también se trata como
base legada (compara y marca), no como base vacía.

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

> **Peligro con el baseline:** `alembic downgrade base` borra las 10 tablas y
> todos los datos. Nunca lo uses para “revertir un deploy” en producción. El `downgrade()` del baseline mira el **target real** de la
> conexión (`op.get_bind().engine.url`), no `ENTORNO` ni `RENDER`: solo se
> permite si el host es local (`localhost`, `127.0.0.1`, `::1` o socket Unix)
> **o** si defines `PERMITIR_DOWNGRADE_BASELINE=1`. Un portátil con
> `ENTORNO=local` apuntando a Supabase también queda bloqueado.
>
> ```bash
> # base local: pasa el guard
> alembic downgrade base
>
> # base remota (por ejemplo Supabase): solo con opt-in explícito
> PERMITIR_DOWNGRADE_BASELINE=1 alembic downgrade base
> ```

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
.venv/bin/alembic downgrade base    # permitido: el host es 127.0.0.1
.venv/bin/alembic upgrade head

pg_ctl -D "$TMP/data" stop
```

No corras `alembic stamp` contra Supabase sin revisar antes el PR: la versión
marcada debe corresponder al esquema real. Para una base legada, prefiere
`python -m app.db.migrar`, que solo marca si el esquema coincide.
