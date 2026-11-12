# ADR-0003: Telemetría por HTTPS con token en lugar de MQTT

- Estado: Aceptado
- Fecha: 2026-11-11
- Módulo: backend, security

## Contexto
Los sensores simulados tienen que mandar sus lecturas a la nube. En la industria lo común es MQTT con un broker, pero el prototipo se despliega en una PaaS gratuita y tiene una semana de desarrollo.

## Decisión
Cada sensor manda sus lecturas con **`POST /api/telemetria` por HTTPS**, autenticado con un **token propio por sensor**. El simulador corre en una laptop que hace de gateway del restaurante.

## Alternativas consideradas
| Opción | A favor | En contra |
|---|---|---|
| **HTTPS + token** | Funciona en Render sin nada extra, fácil de probar con Swagger, cada petición queda en los logs para el SIEM | Más pesado que MQTT por mensaje |
| MQTT con broker (HiveMQ Cloud, Mosquitto) | Estándar de IoT, ligero, publicación/suscripción | Otro servicio que desplegar y asegurar; Render gratis no acepta conexiones TCP que no sean HTTP |
| OPC UA | Estándar industrial | Pensado para planta de manufactura, demasiado para sensores de temperatura de un restaurante |

## Consecuencias
- Con lecturas cada 5–10 segundos por cámara, el costo extra de HTTP no importa.
- Un token por sensor permite revocar uno solo si se compromete, y la regla SIEM puede detectar si un token se usa desde un lugar raro (ADR-0007).
- Si en el futuro hubiera cientos de sensores, se agregaría un broker MQTT en el gateway y este reenviaría a la API; el contrato de la API no cambia.
