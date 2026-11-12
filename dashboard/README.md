# Módulo 3 — Dashboard e Informática Móvil

Tema 3.4. Responsable: _por definir_.

Dashboard web en React + Vite, pensado primero para celular, desplegado en Vercel. Solo habla con la API a través de [docs/contrato-api.md](../docs/contrato-api.md). Mientras el backend no esté listo, se puede trabajar con datos de ejemplo que sigan exactamente los JSON del contrato.

## Tareas

- [ ] Proyecto React + Vite desplegado en Vercel.
- [ ] Login (JWT) y guardar el token.
- [ ] Vista general: una tarjeta por cámara con temperatura, puerta y color según estado (`en_rango`, `alerta`, `critica`).
- [ ] Fila de KPIs: % en rango 24 h, alertas activas, tiempo de respuesta, valor en riesgo, merma del día y del mes.
- [ ] Detalle de cámara: gráfica de las últimas 2 horas con el rango marcado y sus lotes.
- [ ] Lista de alertas con botón "Atender" (rol `jefe_cocina`).
- [ ] Conexión a `GET /api/stream` con `EventSource` para actualizar todo sin recargar — ver ADR-0004.
- [ ] Probar en celular real (Android y iPhone) y en laptop.
- [ ] Etiqueta "MODO DEMO ×N" cuando `GET /api/health` regrese `escala_tiempo` distinto de 1.
- [ ] Lista corta de alertas de seguridad (`GET /api/seguridad/alertas`) para la demo del SIEM.
- [ ] QR a la URL para la exposición.

## Variables de entorno

`VITE_API_URL` con la URL de la API en Render.
