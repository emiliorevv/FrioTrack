"""Middleware de logs de acceso y bloqueo de IPs (ADR-0006, contrato de la API)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.db.models import IpBloqueada, LogAcceso
from app.db.session import SessionLocal, get_engine

# Credencial que corresponde a cada endpoint de máquina. El JWT de usuario se
# agregará después; mientras tanto el resto de las rutas queda como `ninguna`.
CREDENCIAL_POR_RUTA = {
    "/api/telemetria": "sensor",
    "/api/simulador/tick": "cron",
}


def ip_de_scope(scope: Scope) -> str:
    """Devuelve la IP real del cliente.

    Render agrega la IP al final de `X-Forwarded-For`; el primer valor lo puede
    falsificar el cliente, por eso se usa el último. Sin cabecera se usa la
    conexión directa (`scope["client"]`).
    """
    reenviadas = Headers(scope=scope).get("x-forwarded-for", "")
    if reenviadas:
        partes = [parte.strip() for parte in reenviadas.split(",") if parte.strip()]
        if partes:
            return partes[-1]

    cliente = scope.get("client")
    return cliente[0] if cliente else ""


def ruta_de_scope(scope: Scope) -> str:
    """Ruta sin query string: el token del stream nunca se guarda."""
    return scope.get("path", "")


def _credencial_por_ruta(ruta: str) -> str:
    return CREDENCIAL_POR_RUTA.get(ruta, "ninguna")


def _insertar_log(datos: dict[str, Any]) -> None:
    """Inserta una fila en `logs_acceso`; el llamador captura las excepciones."""
    session = SessionLocal(bind=get_engine())
    try:
        session.add(LogAcceso(**datos))
        session.commit()
    finally:
        session.close()


def _ip_bloqueada(ip: str) -> bool:
    """Consulta `ips_bloqueadas`; el llamador captura las excepciones."""
    session = SessionLocal(bind=get_engine())
    try:
        fila = session.get(IpBloqueada, ip)
        if fila is None:
            return False
        hasta = fila.hasta
        if hasta.tzinfo is None:
            hasta = hasta.replace(tzinfo=UTC)
        return hasta > datetime.now(UTC)
    finally:
        session.close()


class AccesoLogMiddleware:
    """Registra cada petición HTTP y corta con 403 las IPs bloqueadas.

    Es ASGI puro a propósito: no envuelve ni consume el cuerpo de la respuesta,
    así que los eventos SSE salen sin buffering. La latencia se mide hasta
    `http.response.start`, que es lo que se registra para una conexión abierta.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inicio = perf_counter()
        db_activa = get_settings().middleware_acceso_db
        ip = ip_de_scope(scope)
        metodo = scope.get("method", "")
        ruta = ruta_de_scope(scope)
        user_agent = Headers(scope=scope).get("user-agent", "")

        if db_activa and await self._esta_bloqueada(ip):
            respuesta = JSONResponse(
                status_code=403,
                content={"detail": "IP bloqueada temporalmente."},
            )
            await respuesta(scope, receive, send)
            await self._registrar(
                db_activa=db_activa,
                inicio=inicio,
                ip=ip,
                metodo=metodo,
                ruta=ruta,
                status=403,
                credencial=_credencial_por_ruta(ruta),
                sujeto=None,
                user_agent=user_agent,
            )
            return

        registrado = False

        async def enviar(message: Message) -> None:
            nonlocal registrado
            if message["type"] == "http.response.start" and not registrado:
                registrado = True
                estado = scope.get("state", {})
                await self._registrar(
                    db_activa=db_activa,
                    inicio=inicio,
                    ip=ip,
                    metodo=metodo,
                    ruta=ruta,
                    status=message["status"],
                    credencial=estado.get("credencial") or _credencial_por_ruta(ruta),
                    sujeto=estado.get("sujeto"),
                    user_agent=user_agent,
                )
            await send(message)

        await self.app(scope, receive, enviar)

    @staticmethod
    async def _esta_bloqueada(ip: str) -> bool:
        """Si la base falla, la petición sigue: el bloqueo nunca tumba la API."""
        if not ip:
            return False
        try:
            return await run_in_threadpool(_ip_bloqueada, ip)
        except Exception:
            return False

    @staticmethod
    async def _registrar(
        *,
        db_activa: bool,
        inicio: float,
        ip: str,
        metodo: str,
        ruta: str,
        status: int,
        credencial: str,
        sujeto: str | None,
        user_agent: str,
    ) -> None:
        """Escribe la línea JSON en stdout y, si está habilitado, en la tabla."""
        datos: dict[str, Any] = {
            "ts": datetime.now(UTC),
            "ip_origen": ip,
            "metodo": metodo,
            "ruta": ruta,
            "status": status,
            "credencial": credencial,
            "sujeto": sujeto,
            "user_agent": user_agent,
            "latencia_ms": int((perf_counter() - inicio) * 1000),
        }
        salida = {**datos, "ts": datos["ts"].isoformat()}
        print(json.dumps(salida, ensure_ascii=False), flush=True)

        if not db_activa:
            return
        try:
            await run_in_threadpool(_insertar_log, datos)
        except Exception:
            pass  # Un fallo de la base no debe romper la respuesta.
