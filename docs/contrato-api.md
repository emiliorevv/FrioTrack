# Contrato de la API

Este documento es lo único que comparten los tres módulos. El backend lo implementa, el dashboard lo consume y seguridad usa el formato de los logs. Si alguien necesita cambiarlo, abre un PR solo con el cambio a este archivo y lo aprueban los dueños del backend y del dashboard antes de tocar código.

- URL base: `https://<servicio>.onrender.com/api`
- Formato: JSON, fechas en ISO 8601 con zona horaria (`2026-11-18T19:05:00-06:00`), temperaturas en °C, dinero en pesos MXN.
- Documentación interactiva: `/docs` (Swagger que genera FastAPI).
- Tablas de la base: [modelo-datos.md](modelo-datos.md).

## Autenticación

Hay tres tipos de credencial, una por zona. Ninguna sirve para lo que le toca a otra (principio de mínimo privilegio).

| Quién | Credencial | Puede llamar |
|---|---|---|
| Sensor o gateway del restaurante | `Authorization: Bearer <token_sensor>`, un token por sensor | Solo `POST /telemetria` |
| Cloudflare Worker (cron) | `Authorization: Bearer <token_cron>` | Solo `POST /simulador/tick` |
| Usuario del dashboard | `Authorization: Bearer <jwt>` que da `POST /auth/login` o `POST /auth/registro`, dura 8 horas | Lecturas, alertas, lotes, KPIs y stream |

Roles de usuario: `dueno` (ve y opera todo el restaurante y atiende alertas), `jefe_cocina` (ve todo y atiende alertas) y `gerente` (solo consulta, no atiende).

### `POST /auth/login`

Entrega el JWT que usa el dashboard. Siempre está disponible, con `AUTH_REQUERIDA` prendida o apagada.

```json
{ "usuario": "jefe", "password": "..." }
```

Respuesta `200`:
```json
{ "access_token": "<jwt>", "token_type": "bearer", "expira_en_segundos": 28800 }
```

El JWT usa HS256 y lleva `sub` (usuario), `uid` (id del usuario), `rol`, `pwd` (huella corta del hash de la contraseña), `restaurante_id` (tenant del usuario), `es_demo` (`true` si el usuario pertenece al restaurante demo; el frontend lo usa para mostrar el panel de demo sin hardcodear el id), `iat` y `exp`; `JWT_EXPIRA_HORAS` define su vigencia (8 h por defecto). Un cambio de contraseña invalida los tokens anteriores, igual que un usuario borrado o recreado. Si el usuario no existe o la contraseña no coincide, la respuesta es `401` con el mismo mensaje (`Usuario o contraseña incorrectos.`) y `WWW-Authenticate: Bearer`, sin revelar cuál de los dos falló. Tras 10 intentos por IP en 5 minutos el login responde `429` con `Retry-After`.

### `POST /auth/registro`

Alta pública de un restaurante y su usuario dueño. No requiere JWT y funciona con `AUTH_REQUERIDA` prendida o apagada: es la puerta de entrada del producto.

```json
{ "restaurante": "Taquería Norte", "usuario": "dueno@norte.mx", "password": "..." }
```

`restaurante` va de 2 a 120 caracteres y `usuario` de 3 a 64; a ambos se les recortan los espacios de los extremos y un valor que queda vacío es inválido. `usuario` además se guarda en **minúsculas** (`Dueno@Norte.mx` y `dueno@norte.mx` son el mismo login) y es el **identificador de login**, único a nivel global: el dashboard puede pedirlo como correo, pero todavía no existe el campo `email` ni la verificación de correo, así que no se agrega un dato que aún no se valida. `password` va de 8 a 128 caracteres y se guarda hasheada con PBKDF2.

Respuesta `201`, con el mismo formato que el login:
```json
{ "access_token": "<jwt>", "token_type": "bearer", "expira_en_segundos": 28800 }
```

El alta crea el `restaurante` y, en la misma transacción, un `usuario` con rol `dueno` y `restaurante_id` apuntando al tenant recién creado. El restaurante nace **sin cámaras** y el JWT ya trae el `restaurante_id`, así que el dueño entra directo al dashboard de su tenant. Errores:

| Código | Cuándo |
|---|---|
| `409` | El alta no procedió (`No se pudo completar el registro.`), también si dos altas compiten y la unicidad la detecta la base. El mensaje es genérico a propósito: no confirma si el usuario existe; la verificación por correo será la solución completa y, mientras tanto, el rate limit y la regla SIEM de fuerza bruta cubren el abuso |
| `422` | Campos fuera de rango, vacíos o con tipo incorrecto |
| `429` | Más de 5 intentos por IP en una hora, con `Retry-After`; cuentan todos los intentos, también las altas exitosas |

Los `409` y `429` de este endpoint alimentan la regla SIEM de fuerza bruta, que bloquea la IP tras 10 eventos en 5 minutos.

Las rutas de consulta y el stream exigen este JWT cuando `AUTH_REQUERIDA=1`, que es **obligatorio en producción** (la API no arranca en Render sin él). Con `AUTH_REQUERIDA=0`, permitido solo en local y pruebas, quedan abiertas como antes sobre el restaurante demo. Los datos se aíslan por `restaurante_id`: un recurso de otro restaurante responde `404`, igual que uno inexistente. Un token sin el claim `restaurante_id`, o con un tenant distinto al de la fila del usuario, responde `401`; los tokens emitidos antes de este cambio dejan de servir (vigencia máxima 8 h). `POST /telemetria` y `POST /simulador/tick` conservan sus tokens de sensor y de cron, y `GET /health` sigue sin autenticación. Un token ausente, inválido o expirado devuelve `401` con `WWW-Authenticate: Bearer`; un rol sin permiso devuelve `403`.

## Endpoints

### Ingesta

#### `POST /telemetria`
Lo llama el simulador por cada lectura.

```json
{
  "sensor_id": "S-PES-01",
  "camara_id": 1,
  "ts": "2026-11-18T19:05:00-06:00",
  "temperatura_c": 1.4,
  "humedad_pct": 88,
  "puerta_abierta": false
}
```

Respuesta `202`:
```json
{ "lectura_id": 18342, "estado_camara": "en_rango" }
```

Errores: `401` token inválido, `403` el token no corresponde a ese `sensor_id` o a esa cámara, `422` datos fuera de lo físicamente posible (por ejemplo temperatura menor a −40 o mayor a 60).

#### `POST /simulador/tick`
Lo llama el Cloudflare Worker cada minuto. Genera una lectura por cámara con el escenario normal y la procesa igual que `POST /telemetria`, con `sensor_id = "SIM-CRON"`. Se salta las cámaras que recibieron una lectura del simulador en los últimos 2 minutos, para no tapar una falla provocada en la demo, y también las que ya recibieron un tick en los últimos 30 segundos, para no duplicar lecturas si dos ejecuciones se solapan. Solo genera lecturas en modo demo (`ESCALA_TIEMPO > 1`); en producción solo mantiene despierta la API y responde `{ "lecturas": 0, "saltadas": [] }`. Respuesta `202` con `{ "lecturas": 4, "saltadas": [1] }`.

#### `GET /health`
Sin autenticación. Regresa `{ "ok": true, "escala_tiempo": 30 }`. Sirve para despertar Render antes de la demo y para que el dashboard muestre la etiqueta de modo demo.

### Seguridad

#### `GET /seguridad/alertas`
Usuario con cualquier rol. Lista las últimas 20 filas de `alertas_seguridad` para mostrarlas en el dashboard durante la demo del SIEM. El SIEM es global y todavía no guarda el restaurante de cada hallazgo: mientras exista **un solo** restaurante (la demo), el demo ve el feed; en cuanto hay un segundo restaurante todos reciben `[]` hasta que el detector se aísle por restaurante.

### Consulta

Todas las consultas devuelven solo filas del restaurante del JWT (o del restaurante demo con `AUTH_REQUERIDA=0`). Pedir por ID un recurso de otro restaurante responde `404`, igual que uno inexistente.

#### `GET /camaras`
```json
[
  {
    "id": 1,
    "nombre": "Pescados y mariscos",
    "rango_min_c": 0,
    "rango_max_c": 2,
    "min_para_riesgo": 10,
    "min_para_merma": 60,
    "estado": "alerta",
    "ultima_lectura": { "ts": "...", "temperatura_c": 3.1, "humedad_pct": 85, "puerta_abierta": true },
    "valor_en_riesgo_mxn": 4850.00,
    "valor_inventario_mxn": 5970.00
  }
]
```

`valor_en_riesgo_mxn` suma el costo de los lotes `en_riesgo` de la cámara; `valor_inventario_mxn` suma todos sus lotes vigentes, es decir, todos menos los que ya están en `merma`.

#### `GET /camaras/{id}/lecturas?desde=&hasta=`
Lista de lecturas de una cámara para la gráfica. Si no se manda rango, regresa las últimas 2 horas.

#### `GET /lotes?camara_id=&estado=`
```json
[
  { "id": 7, "producto": "Robalo fresco", "camara_id": 1, "cantidad": 12, "unidad": "kg",
    "costo_total_mxn": 3240.00, "caducidad": "2026-11-20", "estado": "en_riesgo",
    "merma_en": null }
]
```

`merma_en` es la fecha en que el lote pasó a `merma` (o `null`); se agregó para que el CRUD de inventario y la marca manual de merma compartan el mismo objeto.

#### `GET /alertas?activas=true`
```json
[
  { "id": 31, "camara_id": 1, "tipo": "temperatura", "abierta_en": "...", "cerrada_en": null,
    "atendida_por": null, "temperatura_max_c": 3.4, "sms_enviados": 1 }
]
```
`tipo` puede ser `temperatura` o `puerta`.

#### `POST /alertas/{id}/atender`
Solo roles `jefe_cocina` o `dueno`. Body `{ "nota": "Se cerró la puerta" }`. Marca quién la atendió y cuánto tardó. Con `AUTH_REQUERIDA=1` se atribuye al usuario del JWT y un `gerente` recibe `403`; con la bandera apagada se atribuye al primer `jefe_cocina` del restaurante de la petición (en la demo, `jefe`). Una alerta de otro restaurante responde `404`.

#### `GET /kpis`
```json
{
  "pct_tiempo_en_rango_24h": 97.3,
  "alertas_activas": 1,
  "tiempo_respuesta_promedio_min": 6.5,
  "valor_en_riesgo_mxn": 4850.00,
  "merma_hoy_mxn": 0,
  "merma_mes_mxn": 1720.00
}
```

### Gestión de cámaras y sensores

Las operaciones de escritura exigen rol `dueno`. Todo se limita al restaurante del JWT: un recurso de otro restaurante responde `404`, igual que uno inexistente. Con `AUTH_REQUERIDA=0` (local y pruebas) se aceptan sin JWT sobre el restaurante demo. Errores comunes: `401` sin JWT válido, `403` rol distinto de `dueno`, `404` recurso inexistente o ajeno, `409` conflicto y `422` datos inválidos.

#### `POST /camaras`
```json
{
  "nombre": "Barra fría",
  "rango_min_c": -5,
  "rango_max_c": 5,
  "min_para_riesgo": 10,
  "min_para_merma": 60
}
```

Respuesta `201` con la misma forma que un elemento de `GET /camaras`:

```json
{
  "id": 6,
  "nombre": "Barra fría",
  "rango_min_c": -5.0,
  "rango_max_c": 5.0,
  "min_para_riesgo": 10,
  "min_para_merma": 60,
  "estado": "en_rango",
  "ultima_lectura": null,
  "valor_en_riesgo_mxn": 0.0,
  "valor_inventario_mxn": 0.0
}
```

Reglas de validación (`422` si no se cumplen): `nombre` de 2 a 120 caracteres después de recortar espacios; `-50 <= rango_min_c < rango_max_c <= 50`; `min_para_riesgo >= 1`; `min_para_merma > min_para_riesgo` (la merma es la etapa siguiente al riesgo). Los nombres duplicados están permitidos: no hay restricción de unicidad.

#### `PATCH /camaras/{id}`
Body parcial con cualquiera de los campos de configuración (`nombre`, `rango_min_c`, `rango_max_c`, `min_para_riesgo`, `min_para_merma`). No acepta `estado`, `ultima_lectura_id` ni `restaurante_id`: enviarlos responde `422`. Las reglas se validan contra la configuración ya guardada. Después de aplicar el cambio se reconcilia el estado con la última lectura: si queda en rango, limpia `fuera_de_rango_desde` y cierra la alerta de temperatura abierta; si queda fuera, arranca una ventana nueva sin abrir alerta (la decide la siguiente lectura o el tick). Respuesta `200` con el mismo objeto que `GET /camaras`.

#### `DELETE /camaras/{id}`
`204` si la cámara no tiene sensores, lotes, lecturas ni alertas. Si tiene dependencias responde `409` con el mensaje `La cámara tiene datos asociados; desactívala o elimina primero sus sensores.` No hay endpoint para desactivar cámaras en esta fase.

#### `GET /sensores`
Cualquier rol autenticado del tenant. Lista los sensores del restaurante:

```json
[
  {
    "id": "S-BARRA-01",
    "camara_id": 6,
    "activo": true,
    "camara_nombre": "Barra fría",
    "ultima_lectura": "2026-11-18T19:05:00+00:00"
  }
]
```

`ultima_lectura` es `null` si el sensor nunca mandó una lectura. **Nunca** se expone `token_hash`: el token en claro solo aparece en el alta y en la rotación.

#### `POST /camaras/{id}/sensores`
Sin body. El servidor genera siempre el id (`S-` + 8 hex); el cliente no puede elegirlo para no sondear ids de otros restaurantes ni reutilizar ids de la demo. Respuesta `201`:

```json
{
  "sensor": { "id": "S-3f9a2c1d", "camara_id": 6, "activo": true },
  "token": "<token en claro>"
}
```

El token es fuerte y **se muestra una sola vez**: la base solo guarda su SHA-256 en `sensores.token_hash`. `404` si la cámara es de otro restaurante. Si el id aleatorio choca (caso excepcional), la API reintenta y, si no logra uno libre, responde `500` con un mensaje claro.

#### `POST /sensores/{id}/rotar-token`
Genera un token nuevo, reemplaza el hash y responde `200` con la misma forma que el alta (`sensor` + `token`). El token anterior deja de autenticar inmediatamente.

#### `PATCH /sensores/{id}`
Body `{ "activo": true|false }`. Respuesta `200` con `{ id, camara_id, activo }`. Con `activo: false`, `POST /telemetria` con ese token responde `403`.

#### `DELETE /sensores/{id}`
`204` si el sensor no tiene lecturas. Si tiene historial responde `409` y sugiere desactivarlo: `El sensor tiene lecturas asociadas; desactívalo en lugar de eliminarlo.`

### Gestión de inventario

La escritura exige rol `dueno` o `jefe_cocina`. Todo se limita al restaurante del JWT a través de la cámara del lote: un lote o una cámara de otro restaurante responde `404`, igual que uno inexistente. Con `AUTH_REQUERIDA=0` (local y pruebas) se aceptan sin JWT sobre el restaurante demo.

#### `POST /lotes`
```json
{
  "producto": "Robalo fresco",
  "camara_id": 1,
  "cantidad": 12.5,
  "unidad": "kg",
  "costo_total_mxn": 3240.50,
  "caducidad": "2026-11-20"
}
```

Respuesta `201` con el mismo objeto que un elemento de `GET /lotes`: `id`, `producto`, `camara_id`, `cantidad`, `unidad`, `costo_total_mxn`, `caducidad`, `estado` y `merma_en`. El estado inicial se calcula con la ventana actual de la cámara: `ok` si está en rango; `en_riesgo` si ya se cumplió `min_para_riesgo`; `merma` (con `merma_en`) si ya se cumplió `min_para_merma`.

Validación (`422` si no se cumple): `producto` de 2 a 120 caracteres después de recortar espacios; `camara_id` entero positivo y cámara del restaurante (`404` si no); `cantidad` decimal mayor que 0 con hasta 2 decimales; `unidad` exactamente `kg`, `l` o `pz`; `costo_total_mxn` decimal mayor o igual a 0 con hasta 2 decimales; `caducidad` una fecha válida (puede ser pasada, para registrar producto ya vencido).

#### `PATCH /lotes/{id}`
Body parcial con cualquiera de `producto`, `camara_id`, `cantidad`, `unidad`, `costo_total_mxn` o `caducidad`. No acepta `estado`, `merma_en` ni `restaurante_id`: enviarlos responde `422`; un `null` explícito también. La configuración mezclada se valida con el mismo esquema del alta. Mover el lote a otra cámara es válido solo si la cámara es del mismo restaurante; si no, `404`. Al mover, el estado del lote se recalcula con la ventana de la cámara destino (un lote en riesgo que llega a una cámara sana vuelve a `ok`, y uno sano que llega a una cámara fuera de rango pasa a riesgo/merma) y se recalcula el estado de ambas cámaras. Un lote en `merma` **no se puede modificar**: responde `409` con `El lote ya está en merma; no se puede modificar del historial.` Respuesta `200` con el objeto del lote.

#### `DELETE /lotes/{id}`
`204` si el lote está `ok` o `en_riesgo`; antes de borrar se recalcula el estado de la cámara. Si ya está en `merma` responde `409` con `El lote ya está en merma; no se puede eliminar del historial.` La merma se conserva para los KPIs y el historial del inventario.

#### `POST /lotes/{id}/merma`
Sin body. Marca `estado: "merma"` y `merma_en` con la hora del servidor. Es la vía para registrar una pérdida manual sin borrar el lote. Es idempotente: si ya estaba en merma conserva la fecha original y devuelve el mismo objeto. Respuesta `200` con el lote.

### Demo

Los endpoints de simulación solo existen cuando `DEMO_HABILITADA=1`: con el flag apagado el router no se registra y cualquier llamada responde **404** sin pedir autenticación. Con el flag encendido, la petición debe pertenecer al restaurante demo (id 1); otro tenant recibe **404**. Requieren el JWT de usuario (como el resto de consultas) y solo los roles `dueno` y `jefe_cocina` pueden usarlos; otro rol recibe **403**. Con `AUTH_REQUERIDA=0` (local y pruebas) se aceptan sobre el tenant demo. Nunca se exponen tokens de sensor: el backend usa directamente el sensor activo de la cámara.

Todas las simulaciones de lecturas corren en segundo plano (no bloquean la respuesta) y usan las mismas reglas que la ingesta real. Una simulación del mismo tipo en curso responde **409**; el registro se libera al terminar y también expira a los 120 s si la tarea nunca llegó a ejecutarse. `recuperar` cancela y espera a las simulaciones de `falla`/`puerta` activas antes de mandar lecturas normales.

#### `POST /demo/falla`
Body opcional `{ "camara_id": 1 }` (default `1`). Simula una falla de compresor en una cámara del seed (`es_demo=true`): las lecturas se calculan con su rango (la primera queda dentro, cerca del máximo, y la segunda ya lo cruza) y suben hasta que abre la alerta de temperatura o se agota el tiempo máximo (60 s, o el umbral de la cámara escalado más 20 s de margen). Con `ESCALA_TIEMPO=30` la alerta aparece alrededor de los 25 s. Respuesta `202`:

```json
{ "mensaje": "Falla de compresor en curso.", "camara_id": 1 }
```

`404` si la cámara no es del tenant demo; `409` si no tiene sensor activo o ya hay una falla en curso.

#### `POST /demo/puerta`
Body opcional `{ "camara_id": 5 }` (default `5`, congelador). Mantiene la puerta abierta y sube la temperatura ligeramente desde el punto medio de su rango, con un paso que deja la secuencia por debajo de `rango_max_c`; así no dispara una alerta de temperatura. Sigue enviando lecturas (normalmente ~8, cada ~1.5 s) hasta que la alerta de puerta abre o se agota el máximo (`min(60 s, umbral + 15 s)`). Con `ESCALA_TIEMPO=30` la alerta de puerta (por tiempo) abre a los ~10 s. Respuesta `202` con el mismo shape. Mismos `404`/`409` que `falla`; una cámara creada por API (`es_demo=false`) responde `409`.

#### `POST /demo/ataque`
Sin body. Inserta una `AlertaSeguridad` simulada de la regla real de fuerza bruta:

```json
{
  "id": 7,
  "regla_id": "3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41",
  "regla": "Fuerza bruta de credenciales en la API",
  "severidad": "high",
  "ts": "2026-11-18T19:05:00+00:00",
  "ip_origen": "203.0.113.66",
  "detalle": {
    "clave": "ip:203.0.113.66",
    "intentos": 12,
    "ventana_s": 300,
    "rutas": ["/api/auth/login", "/api/telemetria"],
    "simulado": true
  },
  "accion": "bloquear_ip"
}
```

`201` con el shape de `GET /seguridad/alertas`. **No** bloquea ninguna IP real: solo inserta el hallazgo para la demo del SIEM.

#### `POST /demo/recuperar`
Sin body. Cancela las simulaciones de `falla`/`puerta` en curso, espera a que terminen y manda una lectura normal al centro del rango de cada cámara demo para cerrar alertas y volver a `en_rango`. Respuesta `202`:

```json
{ "mensaje": "Recuperación en curso.", "camara_id": null }
```

### Tiempo real

#### `GET /stream?token=<jwt>`
Server-Sent Events. Va el token en la URL porque `EventSource` del navegador no deja mandar headers. Con `AUTH_REQUERIDA=1` el token se valida y, si falta o es inválido, la conexión responde `401`; con la bandera apagada se acepta sin token. La conexión solo recibe eventos de las cámaras de su restaurante. La conexión se queda abierta y la API manda estos eventos:

| Evento | Cuándo | `data` |
|---|---|---|
| `lectura` | Cada lectura procesada | `{ camara_id, ts, temperatura_c, humedad_pct, puerta_abierta, estado_camara }` |
| `alerta_abierta` | Se abre una alerta | El objeto de la alerta |
| `alerta_cerrada` | La cámara vuelve a rango o la atienden | El objeto de la alerta |
| `lote_actualizado` | Un lote cambia de estado | El objeto del lote |
| `notificacion` | Se abre una alerta o lotes pasan a merma | `{ canal, tipo, camara_id, mensaje, ts, url }` (`canal` es `"simulado"`; `tipo` es `alerta_temperatura`, `alerta_puerta` o `merma`) |
| `kpis` | Cada 30 segundos | El mismo objeto que `GET /kpis`, calculado para el restaurante de la conexión |

Ejemplo de lo que llega por la conexión:
```
event: lectura
data: {"camara_id":1,"ts":"2026-11-18T19:05:00-06:00","temperatura_c":3.1,"humedad_pct":85,"puerta_abierta":true,"estado_camara":"alerta"}

event: notificacion
data: {"canal":"simulado","tipo":"alerta_temperatura","camara_id":1,"mensaje":"FríoTrack: Cámara Pescados y mariscos a 3.4 °C hace 10 min. $4,850 en riesgo.","ts":"2026-11-18T19:05:00+00:00","url":"http://localhost:5173"}

```

## Estados

| Entidad | Estados |
|---|---|
| Cámara | `en_rango`, `alerta` (fuera de rango o puerta abierta, todavía sin riesgo), `critica` (hay lotes en riesgo, o merma con la temperatura aún fuera de rango) |
| Lote | `ok`, `en_riesgo`, `merma` |
| Alerta | abierta (`cerrada_en` nulo) o cerrada |

## Logs de acceso (para el módulo de seguridad)

La API escribe una línea JSON por petición en la salida estándar (Render la guarda en sus logs) y también en la tabla `logs_acceso`. El módulo de seguridad escribe sus reglas SIEM sobre este formato.

```json
{
  "ts": "2026-11-18T03:12:44-06:00",
  "ip_origen": "187.190.12.4",
  "metodo": "POST",
  "ruta": "/api/telemetria",
  "status": 401,
  "credencial": "sensor",
  "sujeto": "S-PES-01",
  "user_agent": "python-httpx/0.27",
  "latencia_ms": 12
}
```

`credencial` es `sensor`, `cron`, `usuario`, `registro` o `ninguna`. `sujeto` es el `sensor_id`, el usuario o `null`.

En producción el access log de uvicorn se desactiva (`--no-access-log`, coordinado con el `render.yaml` del PR #42): el middleware de la API es el único que registra y nunca incluye el query string, así que el JWT de `?token=` no aparece en los logs. `GET /health` queda fuera del middleware: no escribe en `logs_acceso` ni consulta o aplica bloqueos de IP.
