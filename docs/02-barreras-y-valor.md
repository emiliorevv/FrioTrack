# 02 — Barreras y valor conectado

Temas 3.6 y 4.4. Lo trabaja todo el equipo; este es el punto de partida.

## Barreras técnicas (sistemas legacy)

| Barrera | Por qué pasa | Cómo la resuelve la arquitectura |
|---|---|---|
| Equipos de frío sin conectividad | Las cámaras y refrigeradores comerciales normalmente solo traen un termostato con pantalla, sin red | Sensores externos que se pegan a la cámara y mandan datos a un gateway; no hay que cambiar el equipo |
| Inventario en hoja de cálculo o en un punto de venta viejo | Muchos restaurantes usan un sistema de punto de venta que no tiene API, o llevan el inventario en Excel | El backend tiene su propio módulo de inventario (lotes) que emula el ERP; después se puede importar un CSV del sistema actual |
| Internet inestable en el restaurante | La red del restaurante es la misma de la terminal de pagos y los clientes | El gateway puede guardar lecturas y reenviarlas cuando vuelva la conexión (mejora para después del Alfa) |
| Red plana | Cámaras de seguridad, terminal de pago, Wi-Fi de clientes y sensores en la misma red | Segmentación IDMZ y Zero Trust (ADR-0006): los sensores no ven nada más y solo pueden hablar con la API |

## Barreras culturales

| Barrera | Cómo se ve | Qué hacemos |
|---|---|---|
| "Siempre lo hemos hecho con la hoja" | El personal no ve por qué cambiar algo que "funciona" | Mostrar el dinero en riesgo en pesos, no solo temperaturas |
| Miedo a que el sistema sirva para culpar | Los cocineros piensan que el registro es para castigar al que dejó la puerta abierta | Las alertas van al jefe de cocina y el objetivo es salvar el producto, no buscar culpables |
| Fatiga de alertas | Si llegan demasiados SMS, se ignoran | Un SMS al abrir la alerta y otro solo si pasa a merma; umbrales de tiempo por cámara |
| Poca costumbre de usar datos | Las decisiones se toman por experiencia | KPIs simples en el dashboard: % de tiempo en rango, merma del mes, tiempo de respuesta |

## Valor conectado

Sin conexión, el control de temperatura es un trámite. Con la arquitectura conectada pasa a ser una herramienta de negocio:

1. **De reaccionar a prevenir.** El jefe de cocina se entera en minutos, no a la mañana siguiente, y puede salvar el producto moviéndolo a otra cámara.
2. **Merma medida en pesos.** Al cruzar temperaturas con lotes, el restaurante sabe cuánto pierde, en qué cámara y por qué. Eso no lo puede hacer una hoja en la puerta.
3. **Evidencia para inspecciones.** Historial continuo y automático, sin huecos.
4. **Mantenimiento con datos.** Si una cámara tarda cada vez más en recuperar su temperatura después de abrir la puerta, es señal de que el compresor está fallando antes de que se descomponga.
5. **Servicio escalable.** La misma plataforma puede ofrecerse a varios restaurantes como servicio mensual (modelo SaaS), que es la ventaja competitiva frente a un termómetro con alarma local.

## Métricas para medir el valor

- Merma por refrigeración en pesos al mes (antes y después).
- Porcentaje del tiempo en rango por cámara.
- Tiempo promedio entre que se abre una alerta y alguien la atiende.
