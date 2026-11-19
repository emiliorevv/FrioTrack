# Modo demo y guion de la demostración

## El problema

La exposición dura 6 minutos, pero las reglas reales tardan más: la cámara de pescado pasa a "en riesgo" a los 10 minutos y a merma a la hora, y la puerta tarda 5 minutos en alertar. Con los tiempos reales nunca se vería una alerta, una notificación ni una merma en vivo.

## La solución: escala de tiempo

El backend lee la variable de entorno **`ESCALA_TIEMPO`** (por defecto `1`). Todos los tiempos de las reglas (`min_para_riesgo`, `min_para_merma` y los 5 minutos de puerta) se dividen entre ese número:

```
segundos_efectivos = minutos_configurados × 60 / ESCALA_TIEMPO
```

Con **`ESCALA_TIEMPO=30`** (cada minuto de las reglas dura 2 segundos):

| Cámara | En riesgo | Merma |
|---|---|---|
| Pescados y mariscos | 20 s | 2 min |
| Carnes y aves | 30 s | 4 min |
| Lácteos | 40 s | 6 min |
| Verduras y frutas | 1 min | 8 min |
| Congelador | 40 s | 4 min |
| Puerta abierta (todas) | 10 s | — |

Reglas para que no se rompa nada:
- Los rangos de temperatura **no** se escalan, solo los tiempos.
- Lo que se configura en la base sigue siendo el valor real (10, 60, etc.); la escala solo se aplica al calcular. Así, para volver a "producción" basta con `ESCALA_TIEMPO=1`.
- El dashboard muestra la etiqueta `MODO DEMO ×30 · 1 min de regla = 2 s reales` cuando `GET /health` regresa una escala válida (`> 0` y distinta de 1). En pantallas angostas (hasta 639 px) se muestra solo `MODO DEMO ×30`; la explicación completa queda en el texto accesible y en el `title`.
- El detector SIEM **no** se escala: sus ventanas (5 minutos para fuerza bruta) ya caben en la demo.

## Cómo se activa

Los endpoints de simulación viven en `/api/demo/*` y solo existen para el restaurante demo (id 1). El interruptor es **`DEMO_HABILITADA`**:

- En Render, define `DEMO_HABILITADA=1` en el panel para la demo actual y `0` en producción real. `render.yaml` usa `sync: false`, así que el blueprint no pisa lo que pongas en el panel.
- En local, `.env` puede llevar `DEMO_HABILITADA=1`; `.env.example` la deja en `0`.
- Con el flag en `0`, el router ni siquiera se registra: los cuatro endpoints responden **404** sin pedir autenticación y no queda ninguna puerta de simulación abierta.

La cuenta demo `dueno` (rol `dueno`) y el usuario `jefe` (rol `jefe_cocina`) ven el panel y pueden lanzar las simulaciones; `gerente` recibe **403**. Con el login activo (`AUTH_REQUERIDA=1`) hace falta el JWT. El claim `es_demo` del token permite al frontend mostrar el panel sin hardcodear el id del restaurante. El backend resuelve el sensor de cada cámara y **nunca manda tokens de sensor al dashboard**. Solo se pueden simular cámaras del seed (`es_demo=true`); una cámara creada por API queda fuera de la demo y responde **409**.

El seed garantiza la cuenta `dueno` también en bases que ya tenían cámaras: `python -m app.db.init_db` agrega los usuarios demo que falten sin tocar los existentes.

## Los botones (endpoints)

El dashboard llama a estos endpoints; todos responden `202` (o `201` en el ataque) y trabajan en segundo plano:

| Botón | Endpoint | Qué hace | Qué se ve |
|---|---|---|---|
| **Falla de compresor** | `POST /api/demo/falla` | Lecturas cada ~1.8 s relativas al rango de la cámara (la segunda ya cruza el máximo), hasta que abre la alerta o se agota el máximo de 60 s (o el umbral de la cámara + 20 s) | La tarjeta pasa a amarilla, luego roja; notificación simulada, lotes en riesgo y alerta para atender |
| **Puerta abierta** | `POST /api/demo/puerta` | ~8 lecturas con la puerta abierta a la temperatura normal de esa cámara (punto medio de su rango) | Alerta de puerta a los ~10 s, sin disparar la de temperatura |
| **Ataque SIEM** | `POST /api/demo/ataque` | Inserta un hallazgo de fuerza bruta simulado (IP de documentación) | La alerta aparece en el panel de seguridad; **no** bloquea ninguna IP real |
| **Recuperar** | `POST /api/demo/recuperar` | Cancela falla/puerta en curso, espera a que terminen y manda una lectura normal a cada cámara demo | Las alertas se cierran, las cámaras vuelven a verde y no siguen subiendo |

`falla` usa la cámara 1 por defecto y `puerta` la 5; ambos aceptan `{ "camara_id": N }`, pero solo de cámaras del seed. Si ya hay una simulación del mismo tipo en curso, el endpoint responde **409**; el registro se libera al terminar y expira a los 120 s si la tarea nunca llegó a ejecutarse. Una cámara sin sensor activo o creada por API responde **409**, y una cámara de otro restaurante **404**.

## Cómo conviven los botones y el cron

- El Cloudflare Worker llama a `/simulador/tick` cada minuto y genera lecturas **normales** solo para las cámaras del seed (`es_demo=true`).
- El tick **solo genera en modo demo** (`ESCALA_TIEMPO > 1`). En producción no inventa lecturas: solo mantiene Render despierto y responde `{lecturas: 0, saltadas: []}`.
- Si una cámara recibió una lectura real del simulador (cualquier `sensor_id` distinto de `SIM-CRON`) en los últimos 2 minutos, el tick **se la salta**. Así el cron no "arregla" la temperatura de una falla que se está provocando en vivo.
- Si dos ticks se solapan (por ejemplo, por el cold start de Render), el segundo **se salta** las cámaras que ya recibieron un tick en los últimos 30 segundos.

## Guion sugerido (6 minutos)

| Minuto | Quién | Qué se muestra |
|---|---|---|
| 0:00–1:00 | Integrante 1 | El problema y la arquitectura (diagrama del README) |
| 1:00–2:00 | Integrante 2 | Dashboard en el celular proyectado; QR para que el profe lo abra; KPIs moviéndose en vivo |
| 2:00–3:30 | Integrante 2 | Botón **Falla de compresor**: la tarjeta se pone amarilla, luego roja, aparece la notificación simulada, los pesos en riesgo y la alerta; se atiende desde el celular |
| 3:30–4:30 | Integrante 3 | Diagrama IDMZ y regla Sigma; botón **Ataque SIEM** y la alerta aparece en el panel; se explica que la IP es de documentación y no se bloquea nada real |
| 4:30–5:30 | Integrante 1 | Barreras legacy y culturales, valor conectado, por qué PaaS |
| 5:30–6:00 | Todos | **Recuperar** para dejar la demo en verde y cierre |

Plan B si falla internet: video grabado de la misma demo (la rúbrica lo acepta, pero baja la calificación del criterio 4, así que es solo emergencia).

## Antes de exponer

1. 30 minutos antes: abrir la API para que Render despierte y revisar `/health`.
2. Confirmar `ESCALA_TIEMPO=30` y `DEMO_HABILITADA=1` en Render.
3. Entrar con la cuenta demo (`dueno` o `jefe`) y pulsar **Recuperar** para empezar en verde.
4. Confirmar que el canal de notificaciones es el simulado: la notificación aparece en el dashboard y no se manda ningún SMS (Twilio queda para producción).
5. Desbloquear la IP del salón si quedó bloqueada en un ensayo.

## Apagar la demo

Cuando la demo ya no se use, pon `DEMO_HABILITADA=0` (o elimina la variable) y redespliega. Los endpoints `/api/demo/*` responden `404`; el resto de la API y el dashboard siguen funcionando igual.
