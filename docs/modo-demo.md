# Modo demo y guion de la demostración

## El problema

La exposición dura 6 minutos, pero las reglas reales tardan más: la cámara de pescado pasa a "en riesgo" a los 10 minutos y a merma a la hora, y la puerta tarda 5 minutos en alertar. Con los tiempos reales nunca se vería una alerta, un SMS ni una merma en vivo.

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
- El dashboard muestra una etiqueta "MODO DEMO ×30" cuando la escala es distinta de 1 (`GET /health` regresa `{ "escala_tiempo": 30 }`).
- El detector SIEM **no** se escala: sus ventanas (5 minutos para fuerza bruta) ya caben en la demo.

## Cómo conviven el simulador y el cron

- El Cloudflare Worker llama a `/simulador/tick` cada minuto y genera lecturas **normales**.
- El tick **solo genera en modo demo** (`ESCALA_TIEMPO > 1`). En producción no inventa lecturas: solo mantiene Render despierto y responde `{lecturas: 0, saltadas: []}`.
- Si una cámara recibió una lectura real del simulador (cualquier `sensor_id` distinto de `SIM-CRON`) en los últimos 2 minutos, el tick **se la salta**. Así el cron no "arregla" la temperatura de una falla que se está provocando en vivo.
- Si dos ticks se solapan (por ejemplo, por el cold start de Render), el segundo **se salta** las cámaras que ya recibieron un tick en los últimos 30 segundos.

## Escenarios del simulador

| Escenario | Qué hace | Qué se ve |
|---|---|---|
| `normal` | Temperatura en el centro del rango con ruido de ±0.3 °C, puerta cerrada | Todo verde |
| `puerta_abierta --camara N` | Puerta abierta y la temperatura sube 0.2 °C por lectura | Alerta de puerta a los 10 s, luego fuera de rango |
| `falla_compresor --camara N` | Puerta cerrada y la temperatura sube 0.4 °C por lectura sin parar | En riesgo, SMS y, si se deja correr, merma con su costo |
| `recuperar --camara N` | Regresa la temperatura al rango poco a poco | La alerta se cierra y los lotes en riesgo vuelven a `ok` |

Intervalo por defecto: una lectura cada 3 segundos por cámara.

## Guion sugerido (6 minutos)

| Minuto | Quién | Qué se muestra |
|---|---|---|
| 0:00–1:00 | Integrante 1 | El problema y la arquitectura (diagrama del README) |
| 1:00–2:00 | Integrante 2 | Dashboard en el celular proyectado; QR para que el profe lo abra; KPIs moviéndose en vivo |
| 2:00–3:30 | Integrante 2 | `falla_compresor --camara 1`: la tarjeta se pone amarilla, luego roja, llega el SMS al celular, aparecen los pesos en riesgo; se atiende la alerta desde el celular |
| 3:30–4:30 | Integrante 3 | Diagrama IDMZ y regla Sigma; se corre el script de ataque y el detector bloquea la IP; se ve en el dashboard |
| 4:30–5:30 | Integrante 1 | Barreras legacy y culturales, valor conectado, por qué PaaS |
| 5:30–6:00 | Todos | Cierre |

Plan B si falla internet: video grabado de la misma demo (la rúbrica lo acepta, pero baja la calificación del criterio 4, así que es solo emergencia).

## Antes de exponer

1. 30 minutos antes: abrir la API para que Render despierte y revisar `/health`.
2. Confirmar `ESCALA_TIEMPO=30` en Render.
3. Correr `recuperar` en todas las cámaras para empezar en verde.
4. Verificar que el celular que recibe los SMS esté verificado en Twilio.
5. Desbloquear la IP del salón si quedó bloqueada en un ensayo.
