# Módulo 2 — Ciberseguridad IT/OT y Diseño SOC

Tema 3.5. Responsable: _por definir_.

Diseño de red IDMZ / Zero Trust y reglas SIEM sobre los logs de acceso de la API. Las tablas que lee y escribe (`logs_acceso`, `lecturas`, `alertas_seguridad`, `ips_bloqueadas`) están en [docs/modelo-datos.md](../docs/modelo-datos.md#seguridad-soc). El formato de los logs está en [docs/contrato-api.md](../docs/contrato-api.md#logs-de-acceso-para-el-módulo-de-seguridad).

## Tareas
- [x] Diagrama de segmentación en draw.io ([`diagramas/idmz.drawio`](diagramas/idmz.drawio) + [PNG](diagramas/idmz.png), también hay [SVG](diagramas/idmz.svg)) con las zonas, VLANs y flujos de puertos de ADR-0006.
- [x] Reglas en formato Sigma en [`siem/`](siem/) (las tres de ADR-0007): fuerza bruta de tokens, token de sensor desde IP desconocida y lecturas imposibles.
- [x] Detector en Python ([`detector/`](detector/)) que lee `logs_acceso` cada minuto, aplica las reglas y registra la alerta con su severidad y acción.
- [x] Script de ataque para la demo ([`ataque.py`](ataque.py)): manda 15 peticiones con tokens falsos y dispara la regla.
- [x] Texto de la sección de seguridad para el reporte PDF en [docs/reporte/seguridad.md](../docs/reporte/seguridad.md).

## Cómo correrlo

Desde la raíz del repo, con la base migrada y `backend/.venv` instalado:

```bash
# Una pasada sin escribir en la base (ver qué detectaría)
PYTHONPATH=. backend/.venv/bin/python -m security.detector --once --dry-run

# Una pasada que sí registra alertas y bloqueos
PYTHONPATH=. backend/.venv/bin/python -m security.detector --once

# Cada 60 segundos hasta Ctrl+C
PYTHONPATH=. backend/.venv/bin/python -m security.detector --intervalo 60

# Ataque de demo: 15 tokens falsos desde 127.0.0.2
PYTHONPATH=. backend/.venv/bin/python security/ataque.py --intentos 15
```

En macOS, el ataque requiere crear el alias una vez por arranque: `sudo ifconfig lo0 alias 127.0.0.2 up`. La guía completa (orden de la demo, opciones, resultados medidos y limitaciones) está en [docs/reporte/seguridad.md](../docs/reporte/seguridad.md#demo-de-ataque-y-respuesta).
