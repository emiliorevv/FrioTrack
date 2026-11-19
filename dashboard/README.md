# Módulo 3 — Dashboard e Informática Móvil

Dashboard web en React + Vite, pensado primero para celular. Habla con la API de FríoTrack mediante [docs/contrato-api.md](../docs/contrato-api.md).

## Despliegue

- API: https://friotrack-api-sw23.onrender.com
- Dashboard: https://friotrack-dashboard.vercel.app
- Swagger: https://friotrack-api-sw23.onrender.com/docs

## Cuentas demo

Todas usan la contraseña `friotrack-demo` y pertenecen al restaurante demo:

| Usuario | Rol | Uso |
| --- | --- | --- |
| `jefe` | Jefe de cocina | Operación y atención de alertas |
| `dueno` | Dueño | Configuración, inventario y demo |
| `gerente` | Gerente | Solo lectura |

## Funcionalidades

- Login JWT con sesión persistida y protección de rutas.
- Registro de restaurante + dueño (sign-up multi-tenant).
- Vista general por cámara: temperatura, puerta, estado y tendencia.
- KPIs de las últimas 24 h, alertas activas, valor en riesgo y merma.
- Alertas operativas con acción “Atender” para jefe de cocina/dueño.
- Panel SIEM con las alertas de seguridad del detector.
- Configuración de cámaras y sensores por el dueño: rangos, tiempos, tokens de un solo uso.
- Inventario y merma: alta, edición, movimiento entre cámaras, merma y borrado.
- Actualización en vivo por SSE y respaldo por polling.
- Panel de simulación para la demo.

## Panel Demo

Visible solo para `dueno` y `jefe_cocina` del restaurante demo. Desde el botón **Demo** del header se pueden lanzar simulaciones y recuperar el estado:

- **Simular falla de compresor**: sube la temperatura de una cámara demo hasta abrir una alerta.
- **Simular puerta abierta**: mantiene la puerta abierta en el congelador para abrir su alerta.
- **Simular ataque SIEM**: inserta una alerta de seguridad simulada (`detalle.simulado=true`).
- **Recuperar cámaras**: envía lecturas normales y cierra las alertas abiertas.

Los endpoints `/api/demo/*` solo existen con `DEMO_HABILITADA=1` y en el tenant demo. En una instalación real se apaga esa variable: el panel y las rutas responden 404, y el frontend muestra “La simulación no está disponible en este entorno.”.

## Variables de entorno

- `VITE_API_URL`: URL base de la API, por ejemplo `https://friotrack-api-sw23.onrender.com/api`.
- `VITE_MOSTRAR_DEMO=1`: muestra los usuarios demo en el login fuera de desarrollo. Sin esta variable, producción solo muestra la pista en DEV; nunca se publica la contraseña fuera de DEV. Las credenciales están en este README.

## Desarrollo local

```bash
npm install
VITE_API_URL=http://127.0.0.1:8000/api npm run dev
```

El backend debe correr con `AUTH_REQUERIDA=1` y el seed cargado (`SEED_PASSWORD=friotrack-demo`). Para probar el panel demo, agrega `DEMO_HABILITADA=1` en el backend.

## Calidad

```bash
npm run lint
npm test
npm run build
npm run format:check
```
