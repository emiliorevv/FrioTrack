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
| Usuario del dashboard | `Authorization: Bearer <jwt>` que da `POST /auth/login`, dura 8 horas | Lecturas, alertas, lotes, KPIs y stream |

Roles de usuario: `jefe_cocina` (ve todo y atiende alertas) y `gerente` (ve todo, no atiende alertas).

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
Lo llama el Cloudflare Worker cada minuto. Genera una lectura por cámara con el escenario normal y la procesa igual que `POST /telemetria`, con `sensor_id = "SIM-CRON"`. Se salta las cámaras que recibieron una lectura del simulador en los últimos 2 minutos, para no tapar una falla provocada en la demo. Respuesta `202` con `{ "lecturas": 4, "saltadas": [1] }`.

#### `GET /health`
Sin autenticación. Regresa `{ "ok": true, "escala_tiempo": 30 }`. Sirve para despertar Render antes de la demo y para que el dashboard muestre la etiqueta de modo demo.

### Seguridad

#### `GET /seguridad/alertas`
Usuario con cualquier rol. Lista las últimas 20 filas de `alertas_seguridad` para mostrarlas en el dashboard durante la demo del SIEM.

### Consulta

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
    "valor_en_riesgo_mxn": 4850.00
  }
]
```

#### `GET /camaras/{id}/lecturas?desde=&hasta=`
Lista de lecturas de una cámara para la gráfica. Si no se manda rango, regresa las últimas 2 horas.

#### `GET /lotes?camara_id=&estado=`
```json
[
  { "id": 7, "producto": "Robalo fresco", "camara_id": 1, "cantidad": 12, "unidad": "kg",
    "costo_total_mxn": 3240.00, "caducidad": "2026-11-20", "estado": "en_riesgo" }
]
```

#### `GET /alertas?activas=true`
```json
[
  { "id": 31, "camara_id": 1, "tipo": "temperatura", "abierta_en": "...", "cerrada_en": null,
    "atendida_por": null, "temperatura_max_c": 3.4, "sms_enviados": 1 }
]
```
`tipo` puede ser `temperatura` o `puerta`.

#### `POST /alertas/{id}/atender`
Solo rol `jefe_cocina`. Body `{ "nota": "Se cerró la puerta" }`. Marca quién la atendió y cuánto tardó.

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

### Tiempo real

#### `GET /stream?token=<jwt>`
Server-Sent Events. Va el token en la URL porque `EventSource` del navegador no deja mandar headers. La conexión se queda abierta y la API manda estos eventos:

| Evento | Cuándo | `data` |
|---|---|---|
| `lectura` | Cada lectura procesada | `{ camara_id, ts, temperatura_c, humedad_pct, puerta_abierta, estado_camara }` |
| `alerta_abierta` | Se abre una alerta | El objeto de la alerta |
| `alerta_cerrada` | La cámara vuelve a rango o la atienden | El objeto de la alerta |
| `lote_actualizado` | Un lote cambia de estado | El objeto del lote |
| `kpis` | Cada 30 segundos | El mismo objeto que `GET /kpis` |

Ejemplo de lo que llega por la conexión:
```
event: lectura
data: {"camara_id":1,"ts":"2026-11-18T19:05:00-06:00","temperatura_c":3.1,"humedad_pct":85,"puerta_abierta":true,"estado_camara":"alerta"}

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

`credencial` es `sensor`, `cron`, `usuario` o `ninguna`. `sujeto` es el `sensor_id`, el usuario o `null`.
