"""Middleware de logs de acceso y bloqueo de IPs (ADR-0006, contrato de la API)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from time import monotonic, perf_counter
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

# La caché evita una consulta a `ips_bloqueadas` por petición. Con este TTL una
# IP recién bloqueada tarda como máximo 15 s en recibir 403 (y una desbloqueada
# en volver a pasar).
TTL_BLOQUEO_SEG = 15.0
# Un fallo de base se avisa una vez por minuto y por operación: sin el límite,
# un Supabase caído escribiría un warning por cada petición.
SEGUNDOS_ENTRE_AVISOS = 60.0
# Tope de la caché para que muchas IPs distintas no la hagan crecer sin fin.
MAX_ENTRADAS_CACHE = 1024

logger = logging.getLogger(__name__)

# Logger propio para la línea JSON de acceso: stdout, sin prefijos ni
# propagación, y sin `print`, que bloquearía el event loop con un pipe lento.
logger_salida = logging.getLogger("friotrack.acceso")
if not logger_salida.handlers:
    manejador_stdout = logging.StreamHandler(sys.stdout)
    manejador_stdout.setFormatter(logging.Formatter("%(message)s"))
    logger_salida.addHandler(manejador_stdout)
    logger_salida.setLevel(logging.INFO)
    logger_salida.propagate = False

_cache_bloqueos: dict[str, tuple[bool, float]] = {}
_ultimo_aviso: dict[str, float] = {}
_tareas_registro: set[asyncio.Task[None]] = set()


def ip_de_scope(scope: Scope) -> str:
    """Devuelve la IP real del cliente.

    `X-Forwarded-For` solo se obedece en producción, donde Render (el proxy de
    confianza) agrega la IP al final de la cadena; el primer valor lo puede
    falsificar el cliente y por eso se usa el último. En local la cabecera se
    ignora: cualquiera podría inventar su IP en los logs y en el bloqueo.
    """
    if get_settings().es_produccion():
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


def _headers_cors(scope: Scope) -> dict[str, str]:
    """CORS para respuestas que no pasan por `CORSMiddleware` (el 403).

    Este middleware queda por fuera de CORS, así que el navegador necesita que
    el 403 traiga la cabecera para poder leer el mensaje.
    """
    origen = Headers(scope=scope).get("origin")
    if not origen:
        return {}

    origenes = [item.strip() for item in get_settings().cors_origins.split(",") if item.strip()]
    if "*" in origenes:
        return {"Access-Control-Allow-Origin": "*"}
    if origen in origenes:
        return {"Access-Control-Allow-Origin": origen, "Vary": "Origin"}
    return {}


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


def _purgar_cache(ahora: float) -> None:
    for clave in [clave for clave, (_, expira) in _cache_bloqueos.items() if expira <= ahora]:
        del _cache_bloqueos[clave]
    # Si sigue llena (muchas IPs nuevas en pocos segundos), se vacía: reconstruir
    # una entrada cuesta una sola consulta.
    if len(_cache_bloqueos) >= MAX_ENTRADAS_CACHE:
        _cache_bloqueos.clear()


def _ip_bloqueada_cacheada(ip: str) -> bool:
    """Consulta el bloqueo con caché de TTL corto; corre en el threadpool."""
    ahora = monotonic()
    entrada = _cache_bloqueos.get(ip)
    if entrada is not None and entrada[1] > ahora:
        return entrada[0]

    bloqueada = _ip_bloqueada(ip)
    if len(_cache_bloqueos) >= MAX_ENTRADAS_CACHE:
        _purgar_cache(ahora)
    _cache_bloqueos[ip] = (bloqueada, ahora + TTL_BLOQUEO_SEG)
    return bloqueada


def limpiar_cache_bloqueos() -> None:
    """Vacía la caché de bloqueos y el límite de avisos; lo usan las pruebas."""
    _cache_bloqueos.clear()
    _ultimo_aviso.clear()


def _avisar_fallo(operacion: str, error: BaseException) -> None:
    """Registra un fallo de base con un aviso por minuto y operación."""
    ahora = monotonic()
    if ahora - _ultimo_aviso.get(operacion, 0.0) < SEGUNDOS_ENTRE_AVISOS:
        return
    _ultimo_aviso[operacion] = ahora
    logger.warning(
        "Fallo de base en el middleware de acceso (%s): %s", operacion, error, exc_info=True
    )


async def _insertar_en_segundo_plano(datos: dict[str, Any]) -> None:
    try:
        await run_in_threadpool(_insertar_log, datos)
    except Exception as error:
        _avisar_fallo("registro en logs_acceso", error)


def _programar_insert(datos: dict[str, Any]) -> None:
    """Agenda el INSERT fuera del camino de la respuesta: no frena los headers."""
    tarea = asyncio.create_task(_insertar_en_segundo_plano(datos))
    _tareas_registro.add(tarea)
    tarea.add_done_callback(_tareas_registro.discard)


async def esperar_registros() -> None:
    """Espera las inserciones agendadas; lo usan las pruebas del middleware."""
    while _tareas_registro:
        await asyncio.gather(*tuple(_tareas_registro), return_exceptions=True)
        await asyncio.sleep(0)


def _registrar(
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
    """Emite la línea JSON y agenda la fila en `logs_acceso`.

    El stdout sale en el momento (es barato y el contrato pide una línea por
    petición); el INSERT queda en segundo plano para no esperar a Supabase.
    """
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
    logger_salida.info(json.dumps(salida, ensure_ascii=False))

    if db_activa:
        _programar_insert(datos)


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
                headers=_headers_cors(scope),
            )
            await respuesta(scope, receive, send)
            _registrar(
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
                # Primero salen los headers; después se emite y agenda el log.
                await send(message)
                estado = scope.get("state", {})
                _registrar(
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
                return
            await send(message)

        try:
            await self.app(scope, receive, enviar)
        except Exception:
            # Una ruta que lanza nunca manda `http.response.start`: el 500 lo
            # escribe `ServerErrorMiddleware`, fuera de este middleware. Se
            # registra aquí y se relanza para no cambiar la respuesta.
            if not registrado:
                registrado = True
                estado = scope.get("state", {})
                _registrar(
                    db_activa=db_activa,
                    inicio=inicio,
                    ip=ip,
                    metodo=metodo,
                    ruta=ruta,
                    status=500,
                    credencial=estado.get("credencial") or _credencial_por_ruta(ruta),
                    sujeto=estado.get("sujeto"),
                    user_agent=user_agent,
                )
            raise

    @staticmethod
    async def _esta_bloqueada(ip: str) -> bool:
        """Si la base falla, la petición sigue: el bloqueo nunca tumba la API."""
        if not ip:
            return False
        try:
            return await run_in_threadpool(_ip_bloqueada_cacheada, ip)
        except Exception as error:
            _avisar_fallo("consulta de ips_bloqueadas", error)
            return False
