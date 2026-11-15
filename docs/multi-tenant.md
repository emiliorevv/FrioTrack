# Multi-tenant

FríoTrack atiende varios restaurantes con el mismo despliegue. Este documento
resume cómo se guarda el tenant y cómo se aísla todo lo que ya existe. El
sign-up (`POST /auth/registro`) da de alta restaurantes y su usuario `dueno`;
la verificación de correo y el onboarding visual siguen pendientes.

## Modelo

- `restaurantes` es la raíz: `id`, `nombre`, `creado_en`.
- `restaurante_id` (FK a `restaurantes.id`, `not null`, con índice) vive solo en
  `usuarios` y `camaras`, que son la fuente de verdad.
- `lotes` y `alertas` **no** guardan `restaurante_id`: lo derivan de su cámara
  (`camara_id`), igual que `lecturas` y `sensores`. Así una cámara reasignada de
  restaurante no deja filas huérfanas con un tenant viejo, y no hay dos valores
  que puedan divergir.
- `logs_acceso`, `alertas_seguridad` e `ips_bloqueadas` siguen globales: son el
  SIEM de la plataforma, no datos de un restaurante.

La migración `0002_restaurantes_tenant.py` crea `restaurantes`, inserta el
restaurante demo y alinea su secuencia, agrega `restaurante_id` como nullable a
`usuarios` y `camaras`, hace backfill de todas las filas existentes a 1 y las
deja `not null` con FK e índices. Funciona igual en una base vacía y en una base
que ya estaba en `0001` con datos.

## Demo y auth apagada

- `RESTAURANTE_DEMO_ID = 1` y `NOMBRE_RESTAURANTE_DEMO` viven en
  `backend/app/db/models.py`. La demo se llama `FríoTrack Demo`.
- El seed asigna ese tenant a cámaras y usuarios, y no duplica el restaurante si
  la migración ya lo insertó. Su guard de idempotencia solo mira las cámaras del
  tenant demo: si a la demo le borraron los datos, se repuebla aunque otros
  restaurantes tengan cámaras.
- Si el seed tiene que crear el restaurante demo, después del flush ejecuta
  `setval(pg_get_serial_sequence('restaurantes','id'), MAX(id))`; la migración
  hace lo mismo. Sin eso, el primer restaurante creado sin id chocaría con la PK.
- Con `AUTH_REQUERIDA=0` (local y pruebas) no hay usuario: la dependencia
  `get_restaurante_id` devuelve el restaurante demo, así que la demo se
  comporta igual que antes.

## Sign-up

`POST /auth/registro` es público (no depende de `AUTH_REQUERIDA`) y crea en una
sola transacción un `restaurante` y su usuario con rol `dueno`. El tenant nuevo
nace **sin cámaras ni usuarios adicionales**; el JWT que devuelve el endpoint ya
trae su `restaurante_id`, así que el dueño entra directo al dashboard y ve una
lista vacía hasta que se den de alta cámaras.

- El identificador de login es `usuario` (único global; se guarda en minúsculas
  y el dashboard puede pedirlo como correo). Todavía **no** hay verificación de
  correo ni campo `email`.
- El rate limit es por IP: 5 intentos por hora; cuentan también las altas
  exitosas.
- El resto del onboarding (alta visual de cámaras, invitación de
  `jefe_cocina`/`gerente`, verificación de correo) queda para PRs posteriores.

## Aislamiento

- **JWT**: `crear_token` firma el claim `restaurante_id`. `decodificar_token` lo
  exige y `_usuario_del_token` comprueba que sea un entero positivo y que
  coincida con `usuarios.restaurante_id`; si no, la respuesta es 401. Los tokens
  emitidos antes de este cambio no traen el claim y quedan inválidos (duran 8 h
  como máximo).
- **REST**: `GET /camaras` filtra `Camara.restaurante_id`. `GET /lotes` y
  `GET /alertas` hacen join con `Camara` y filtran `Camara.restaurante_id`.
  Pedir una cámara, sus lecturas, o atender una alerta de otro restaurante
  responde **404**, igual que un recurso inexistente, para no filtrar su
  existencia. La verificación vive en `camara_del_restaurante()` y la reutilizan
  todos los endpoints. `POST /alertas/{id}/atender` acepta los roles
  `jefe_cocina` y `dueno` del JWT; sin JWT elige al primer `jefe_cocina` **del
  tenant de la petición**.
- **KPIs**: `calcular_kpis(db, restaurante_id)` filtra las cinco consultas con
  join a la cámara: lecturas, alertas activas, atendidas, lotes en riesgo y
  mermas.
- **Stream**: el bus es tenant-aware. Cada conexión se suscribe con su
  `restaurante_id` y `EventBus.publicar(evento, data, restaurante_id)` entrega
  solo a las colas de ese restaurante; un evento sin tenant no se entrega a
  nadie (fail closed). Todos los publishers (telemetría, atender alerta,
  notificaciones y KPIs) pasan el tenant de la cámara/alerta. La conexión solo
  calcula un KPI inicial al conectar; los periódicos llegan ya calculados.
- **KPIs periódicos**: una sola tarea recorre los restaurantes con cámaras
  (`SELECT DISTINCT camaras.restaurante_id`), calcula cada KPI una vez por
  tenant y publica el payload a sus conexiones. El costo por ciclo crece con los
  restaurantes, no con las conexiones SSE.
- **Tick**: `POST /simulador/tick` solo genera lecturas simuladas para las
  cámaras del restaurante demo. Los tenants nuevos no reciben tráfico
  inventado; esperan la telemetría de sus sensores.
- **SIEM**: `GET /seguridad/alertas` es global y todavía no guarda el
  restaurante de cada hallazgo. Mientras solo exista el restaurante demo, el
  demo ve el feed; en cuanto hay un segundo restaurante, **nadie** lo ve (lista
  vacía) para no filtrar usuarios, IPs ni detalles entre tenants. Se aislará
  cuando el detector sea tenant-aware.

## Pendientes

- Verificación de correo en el sign-up y onboarding visual (cámaras, usuarios y
  roles) por tenant.
- CRUD de cámaras y usuarios, e invitación de `jefe_cocina`/`gerente`.
- RLS (Row Level Security) en Postgres como segunda barrera, además del filtro
  en la API. Para `lotes` y `alertas`, la política tendrá que hacer el join con
  `camaras` porque no guardan el tenant.
- SIEM aislado por restaurante (columna de tenant en `alertas_seguridad` y
  `logs_acceso`).
- Unicidad de `usuarios.usuario` por restaurante; hoy es global.

## Regla

Toda consulta nueva a `camaras`, `lotes`, `alertas` o `usuarios` debe filtrar
por el `restaurante_id` del tenant de la petición. Si la tabla no tiene la
columna (como `lecturas`, `lotes` o `alertas`), filtra por la cámara dueña con
un join. Un endpoint sin filtro es un bug de aislamiento aunque hoy solo exista
la demo.
