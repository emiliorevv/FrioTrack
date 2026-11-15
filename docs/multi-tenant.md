# Multi-tenant

FríoTrack atiende varios restaurantes con el mismo despliegue. Este documento
resume cómo se guarda el tenant y cómo se aísla todo lo que ya existe. El
sign-up (alta de restaurantes y usuarios) todavía no existe: por ahora solo hay
un tenant real, la demo.

## Modelo

- `restaurantes` es la raíz: `id`, `nombre`, `creado_en`.
- `restaurante_id` (FK a `restaurantes.id`, `not null`, con índice) vive en
  `usuarios`, `camaras`, `lotes` y `alertas`.
- `lecturas` y `sensores` **no** llevan `restaurante_id`: se deriva de la cámara
  (`lecturas.camara_id` / `sensores.camara_id`). Una lectura siempre es de la
  cámara que la recibió.
- `logs_acceso`, `alertas_seguridad` e `ips_bloqueadas` siguen globales: son el
  SIEM de la plataforma, no datos de un restaurante.

La migración `0002_restaurantes_tenant.py` crea `restaurantes`, inserta el
restaurante demo, agrega las columnas como nullable, hace backfill de todas las
filas existentes a 1 y las deja `not null` con FK e índices. Funciona igual en
una base vacía y en una base que ya estaba en `0001` con datos.

## Demo y auth apagada

- `RESTAURANTE_DEMO_ID = 1` y `NOMBRE_RESTAURANTE_DEMO` viven en
  `backend/app/db/models.py`. La demo se llama `FríoTrack Demo`.
- El seed asigna ese tenant a cámaras, lotes y usuarios, y no duplica el
  restaurante si la migración ya lo insertó.
- Con `AUTH_REQUERIDA=0` (local y pruebas) no hay usuario: la dependencia
  `get_restaurante_id` devuelve el restaurante demo, así que la demo se
  comporta igual que antes.

## Aislamiento

- **JWT**: `crear_token` firma el claim `restaurante_id`. `decodificar_token` lo
  exige y `_usuario_del_token` comprueba que sea un entero positivo y que
  coincida con `usuarios.restaurante_id`; si no, la respuesta es 401. Los tokens
  emitidos antes de este cambio no traen el claim y quedan inválidos (duran 8 h
  como máximo).
- **REST**: `GET /camaras`, `GET /lotes` y `GET /alertas` filtran por
  `restaurante_id`. Pedir una cámara, sus lecturas, o atender una alerta de otro
  restaurante responde **404**, igual que un recurso inexistente, para no
  filtrar su existencia. `POST /alertas/{id}/atender` sin JWT elige al primer
  `jefe_cocina` **del tenant de la petición**.
- **KPIs**: `calcular_kpis(db, restaurante_id)` filtra las cinco consultas
  (lecturas por cámara, alertas activas, atendidas, lotes en riesgo y mermas).
- **Stream**: cada conexión recibe el tenant de su JWT. Al conectar carga los
  IDs de cámaras permitidas y descarta los eventos con `camara_id` ajeno; en
  cada evento `kpis` (cada ~30 s) refresca esa lista y recalcula los KPIs de su
  restaurante. La tarea periódica del bus solo publica la señal `kpis`, nunca
  una foto global.
- **Tick**: `POST /simulador/tick` solo genera lecturas simuladas para las
  cámaras del restaurante demo. Los tenants nuevos no reciben tráfico
  inventado; esperan la telemetría de sus sensores.
- **SIEM**: `GET /seguridad/alertas` devuelve el feed global solo al tenant
  demo; los demás reciben `[]` hasta que el detector guarde el restaurante de
  cada hallazgo.

## Pendientes

- Sign-up, alta de restaurantes y CRUD de cámaras/usuarios por tenant.
- RLS (Row Level Security) en Postgres como segunda barrera, además del filtro
  en la API.
- SIEM aislado por restaurante (columna de tenant en `alertas_seguridad` y
  `logs_acceso`).
- Unicidad de `usuarios.usuario` por restaurante; hoy es global.

## Regla

Toda consulta nueva a `camaras`, `lotes`, `alertas` o `usuarios` debe filtrar
por `restaurante_id` del tenant de la petición. Si la tabla no tiene la columna
(como `lecturas`), filtra por la cámara dueña. Un endpoint sin filtro es un bug
de aislamiento aunque hoy solo exista la demo.
