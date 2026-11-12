# ADR-0010: Escala de tiempo para la demo

- Estado: Aceptado
- Fecha: 2026-11-12
- Módulo: backend

## Contexto
Las reglas de negocio usan tiempos reales (de 10 minutos a 4 horas) y la exposición dura 6 minutos. Hay que poder mostrar en vivo una alerta, el SMS y una merma sin cambiar la lógica ni los datos.

## Decisión
Una variable de entorno `ESCALA_TIEMPO` divide todos los tiempos de las reglas al momento de calcular. En la demo se usa `30`. Los valores guardados en la base no cambian. Detalle en [modo-demo.md](../modo-demo.md).

## Alternativas consideradas
| Opción | A favor | En contra |
|---|---|---|
| **Variable de escala** | Un solo cambio, la lógica es la misma que en producción | Hay que acordarse de ponerla y de quitarla |
| Cambiar los minutos en la base para la demo | Nada de código | Se mienten los datos y es fácil olvidar regresarlos |
| Mandar lecturas con `ts` adelantado | Simula el paso del tiempo | Se mezcla con las lecturas del cron y rompe el orden; las reglas usan la hora del servidor |
| Video grabado | Sin riesgo | La rúbrica lo califica como demo fallida |

## Consecuencias
- La demo muestra el flujo completo en unos 2 minutos.
- El dashboard avisa con una etiqueta cuando la escala no es 1, para que nadie confunda la demo con datos reales.
