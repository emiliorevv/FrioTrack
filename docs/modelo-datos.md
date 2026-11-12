# Modelo de datos

Tablas de Postgres (Supabase) que usan el backend y el módulo de seguridad. El backend es dueño de todas; seguridad lee `logs_acceso` y `lecturas`, y escribe solo en `alertas_seguridad` e `ips_bloqueadas`.

Convenciones:
- Fechas en UTC (`timestamptz`). El dashboard las muestra en hora de Mérida.
- Dinero en pesos MXN con `numeric(10,2)`.
- Nombres de tablas y columnas en español, en minúsculas y con guion bajo, igual que el contrato de la API.

## Diagrama

```
camaras 1───* lotes
   │ 1
   ├───* sensores
   ├───* lecturas
   └───* alertas

usuarios                 logs_acceso ──> (lo lee el detector SIEM)
alertas_seguridad        ips_bloqueadas <── (lo escribe el detector, lo lee la API)
```

## Operación (ERP/MES)

### `camaras`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | `serial` PK | 1 a 5 |
| `nombre` | `text` | "Pescados y mariscos" |
| `rango_min_c` | `numeric(4,1)` | |
| `rango_max_c` | `numeric(4,1)` | |
| `min_para_riesgo` | `int` | Minutos fuera de rango para pasar lotes a `en_riesgo` |
| `min_para_merma` | `int` | Minutos fuera de rango para pasar lotes a `merma` |
| `estado` | `text` | `en_rango`, `alerta`, `critica` |
| `fuera_de_rango_desde` | `timestamptz` null | Se llena al salir de rango y se borra al volver |
| `puerta_abierta_desde` | `timestamptz` null | Igual, para la puerta |
| `ultima_lectura_id` | `int` null | FK a `lecturas`, para responder rápido `GET /camaras` |

### `sensores`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | `text` PK | `S-PES-01`, `S-CAR-01`, `S-LAC-01`, `S-VER-01`, `S-CON-01` |
| `camara_id` | `int` FK | Un sensor solo puede escribir en su cámara |
| `token_hash` | `text` | SHA-256 del token; el token en claro nunca se guarda |
| `activo` | `bool` | Revocar un token = poner `false` |

El token en claro vive **solo** en la variable de entorno `SENSOR_TOKENS`, que se
usa para sembrar o rotar sensores. La API y la base guardan únicamente el
SHA-256 en `token_hash`; la autenticación del sensor compara el hash, nunca el
token en claro.

### `lecturas`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | `bigserial` PK | |
| `camara_id` | `int` FK | |
| `sensor_id` | `text` FK | `SIM-CRON` cuando la genera `/simulador/tick` |
| `ts` | `timestamptz` | La hora que manda el sensor |
| `recibida_en` | `timestamptz` | La hora del servidor; **las reglas de tiempo usan esta** para no depender del reloj del sensor |
| `temperatura_c` | `numeric(4,1)` | |
| `humedad_pct` | `numeric(4,1)` | |
| `puerta_abierta` | `bool` | |
| `sospechosa` | `bool` | La marca el detector (regla de lecturas imposibles) |

Índice: `(camara_id, recibida_en desc)`.

### `lotes`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | `serial` PK | |
| `producto` | `text` | "Robalo fresco" |
| `camara_id` | `int` FK | |
| `cantidad` | `numeric(8,2)` | |
| `unidad` | `text` | `kg`, `l`, `pz` |
| `costo_total_mxn` | `numeric(10,2)` | |
| `caducidad` | `date` | |
| `estado` | `text` | `ok`, `en_riesgo`, `merma` |
| `merma_en` | `timestamptz` null | Cuándo pasó a merma; con esto salen los KPIs de merma del día y del mes |

### `alertas`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | `serial` PK | |
| `camara_id` | `int` FK | |
| `tipo` | `text` | `temperatura` o `puerta` |
| `abierta_en` | `timestamptz` | |
| `cerrada_en` | `timestamptz` null | Nulo = activa |
| `temperatura_max_c` | `numeric(4,1)` null | La peor lectura mientras estuvo abierta |
| `atendida_por` | `int` null | FK a `usuarios` |
| `atendida_en` | `timestamptz` null | Para el KPI de tiempo de respuesta |
| `nota` | `text` null | |
| `sms_enviados` | `int` | 1 al abrir, 2 si pasó a merma |

Solo puede haber una alerta abierta por cámara y tipo.

### `usuarios`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | `serial` PK | |
| `usuario` | `text` unique | |
| `password_hash` | `text` | PBKDF2 o bcrypt, nunca en claro |
| `rol` | `text` | `jefe_cocina` o `gerente` |
| `telefono` | `text` null | A dónde llegan los SMS (formato `+52...`) |

## Seguridad (SOC)

### `logs_acceso`
Una fila por petición, con exactamente los campos del formato de logs del [contrato de la API](contrato-api.md#logs-de-acceso-para-el-módulo-de-seguridad).

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `bigserial` PK | |
| `ts` | `timestamptz` | |
| `ip_origen` | `text` | La IP real del cliente: el **último** valor de `X-Forwarded-For` que agrega Render, no el primero, porque el primero lo puede falsificar el cliente |
| `metodo` | `text` | |
| `ruta` | `text` | Sin query string (el token del stream nunca se guarda) |
| `status` | `int` | |
| `credencial` | `text` | `sensor`, `cron`, `usuario`, `ninguna` |
| `sujeto` | `text` null | `sensor_id` o usuario |
| `user_agent` | `text` | |
| `latencia_ms` | `int` | |

Índice: `(ruta, status, ts desc)` y `(ip_origen, ts desc)`.

### `alertas_seguridad`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | `serial` PK | |
| `regla_id` | `text` | El `id` de la regla Sigma que la disparó |
| `regla` | `text` | Título corto |
| `severidad` | `text` | `low`, `medium`, `high`, `critical` (como Sigma) |
| `ts` | `timestamptz` | |
| `ip_origen` | `text` null | |
| `detalle` | `jsonb` | Conteos, sensor, lecturas involucradas |
| `accion` | `text` | `bloquear_ip`, `revocar_token`, `marcar_lecturas` |

### `ips_bloqueadas`
| Columna | Tipo | Notas |
|---|---|---|
| `ip` | `text` PK | |
| `hasta` | `timestamptz` | |
| `motivo` | `text` | `regla_id` que la bloqueó |

La API revisa esta tabla al inicio de cada petición: si la IP está bloqueada y `hasta` no ha pasado, responde `403` sin procesar nada (y lo registra en `logs_acceso`).

## Datos iniciales (seed)

El backend crea las tablas y carga esto si la base está vacía:

- Las 5 cámaras con los rangos y tiempos del README.
- Un sensor por cámara.
- 2 o 3 lotes por cámara con costos realistas (por ejemplo: robalo 12 kg $3,240; camarón 5 kg $1,610; arrachera 10 kg $3,100; pechuga 15 kg $1,650; crema 6 l $420; queso Oaxaca 4 kg $640; lechuga 20 pz $300; cilantro y hierbas $180; papas congeladas 10 kg $520; helado 8 l $760).
- Dos usuarios: `jefe` (`jefe_cocina`) y `gerente` (`gerente`), con contraseña desde una variable de entorno.
