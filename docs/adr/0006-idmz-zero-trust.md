# ADR-0006: Segmentación IDMZ y Zero Trust

- Estado: Aceptado
- Fecha: 2026-11-11
- Módulo: security

## Contexto
En un restaurante típico todo comparte la misma red: sensores, terminal de pagos, computadora del gerente, cámaras de seguridad y Wi-Fi de clientes. Si un cliente o un equipo infectado entra a esa red, puede llegar a los sensores, mandar lecturas falsas o tumbar el sistema. El Tema 3.5 pide separar la parte operativa (OT) de la administrativa (IT) con una IDMZ.

## Decisión
Segmentar la red según el **modelo Purdue / ISA-95** adaptado a un restaurante, y aplicar **Zero Trust**: ninguna conexión se considera confiable por estar "adentro".

### Zonas
| Zona | Qué hay | VLAN |
|---|---|---|
| OT (nivel 0–2) | Sensores de las cámaras | 10 |
| Gateway OT (nivel 2–3) | Laptop o Raspberry que junta las lecturas | 10 |
| IDMZ (nivel 3.5) | Firewall y proxy de salida; único punto que sale a internet desde OT | 15 |
| IT corporativa (nivel 4) | PC del gerente, punto de venta | 20 |
| Invitados | Wi-Fi de clientes, aislada de todo | 30 |
| Nube (nivel 5) | API en Render, Postgres en Supabase, dashboard en Vercel | — |

### Flujos permitidos (todo lo demás se niega)
| Origen | Destino | Puerto | Para qué |
|---|---|---|---|
| Sensores | Gateway | Local (Modbus/serial o HTTP interno) | Lecturas |
| Gateway | Proxy IDMZ | 443 | Reenviar lecturas |
| Proxy IDMZ | API (Render) | 443 TLS | `POST /api/telemetria` únicamente |
| API | Supabase | 5432 TLS | Base de datos |
| API | Twilio | 443 | SMS |
| Celular o PC | Dashboard y API | 443 | Consulta con JWT |
| Wi-Fi invitados | Internet | 80/443 | Nada interno |
| IT corporativa | OT | — | **Negado**: nadie entra a la OT desde la oficina |

### Principios Zero Trust aplicados
- **Identidad por dispositivo:** cada sensor tiene su propio token; un token solo puede escribir en su cámara.
- **Mínimo privilegio:** el token de sensor solo llama a `/telemetria`, el del cron solo a `/simulador/tick`, el JWT de usuario solo lee y atiende alertas.
- **Microsegmentación:** VLANs separadas y flujos de salida explícitos; la OT no acepta conexiones entrantes.
- **Cifrado siempre:** TLS en todos los saltos que salen del restaurante.
- **Verificar y registrar todo:** cada petición queda en `logs_acceso` para el SIEM (ADR-0007).

## Alternativas consideradas
| Opción | A favor | En contra |
|---|---|---|
| **IDMZ + Zero Trust** | Lo que pide el tema; protege la OT aunque la red de IT se comprometa | Requiere un router con VLANs |
| Red plana con firewall perimetral | Lo que tienen hoy | Una vez adentro, todo se ve con todo |
| VPN del restaurante a la nube | Cifra el canal | Confía en todo lo que esté dentro de la VPN, lo contrario a Zero Trust |

## Consecuencias
- En el prototipo las VLANs y el firewall son de diseño (diagrama en `security/diagramas/`); lo que sí se implementa en código son los tokens por sensor, roles, TLS y los logs.
- Un router con VLANs para un restaurante cuesta poco y es la única inversión de red real.
