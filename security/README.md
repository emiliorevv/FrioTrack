# Módulo 2 — Ciberseguridad IT/OT y Diseño SOC

Tema 3.5. Responsable: _por definir_.

Diseño de red IDMZ / Zero Trust y reglas SIEM sobre los logs de acceso de la API. Las tablas que lee y escribe (`logs_acceso`, `lecturas`, `alertas_seguridad`, `ips_bloqueadas`) están en [docs/modelo-datos.md](../docs/modelo-datos.md#seguridad-soc). El formato de los logs está en [docs/contrato-api.md](../docs/contrato-api.md#logs-de-acceso-para-el-módulo-de-seguridad).

## Tareas
- [ ] Diagrama de segmentación en draw.io (`diagramas/idmz.drawio` + PNG exportado) con las zonas, VLANs y flujos de puertos de ADR-0006.
- [ ] Reglas en formato Sigma en `siem/` (las tres de ADR-0007): fuerza bruta de tokens, token de sensor desde IP desconocida y lecturas imposibles.
- [ ] Detector en Python (`detector/`) que lee `logs_acceso` cada minuto, aplica las reglas y registra la alerta con su severidad y acción.
- [ ] Script de ataque para la demo: manda 15 peticiones con tokens falsos y dispara la regla.
- [ ] Texto de la sección de seguridad para el reporte PDF.
