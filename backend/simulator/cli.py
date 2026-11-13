"""Simulador de sensores de FríoTrack.

Uso:
    python -m simulator --escenario normal --camara 1 --intervalo 3 --iteraciones 0
"""

import argparse
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.config import leer_sensor_tokens
from app.db.seed import SENSORES
from simulator.cliente import ClienteHTTP, ErrorAPI, Respuesta
from simulator.escenarios import (
    ESCENARIOS,
    LecturaSimulada,
    azar_aleatorio,
    siguiente_lectura,
)

HUMEDAD_POR_DEFECTO = 80.0
API_URL_POR_DEFECTO = "http://127.0.0.1:8000/api"
# 1 intento + 2 reintentos ante timeout, error de red o 5xx.
INTENTOS_POR_LECTURA = 3
ESPERA_REINTENTO_SEGUNDOS = 1.0


class ErrorConfiguracion(RuntimeError):
    """Falta un dato para arrancar (token, cámara o sensor)."""


class ApiSimulador(Protocol):
    """Las llamadas que el bucle necesita; permite inyectar un doble en pruebas."""

    def listar_camaras(self) -> list[dict[str, Any]]: ...

    def enviar_lectura(self, datos: dict[str, Any], token: str) -> Respuesta: ...

    def cerrar(self) -> None: ...


@dataclass(frozen=True)
class Camara:
    """Datos de `GET /camaras` que usa el simulador."""

    id: int
    rango_min_c: float
    rango_max_c: float
    ultima_temperatura_c: float | None
    ultima_humedad_pct: float | None


def construir_parser() -> argparse.ArgumentParser:
    """Arma la CLI con los valores por defecto de la demo."""
    parser = argparse.ArgumentParser(
        prog="python -m simulator",
        description="Simula los sensores de FríoTrack contra la API.",
    )
    parser.add_argument(
        "--escenario",
        choices=sorted(ESCENARIOS),
        default="normal",
        help="escenario a simular (por defecto: normal)",
    )
    parser.add_argument(
        "--camara",
        type=int,
        default=1,
        help="id de la cámara a simular (por defecto: 1)",
    )
    parser.add_argument(
        "--intervalo",
        type=float,
        default=3.0,
        help="segundos entre lecturas (por defecto: 3)",
    )
    parser.add_argument(
        "--iteraciones",
        type=int,
        default=0,
        help="número de lecturas; 0 es sin límite (por defecto: 0)",
    )
    parser.add_argument(
        "--api-url",
        default=API_URL_POR_DEFECTO,
        help=f"URL base de la API (por defecto: {API_URL_POR_DEFECTO})",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="token del sensor; si se omite, se lee SENSOR_TOKENS del entorno",
    )
    return parser


def _flotante_opcional(valor: object) -> float | None:
    return None if valor is None else float(valor)


def buscar_camara(camaras: list[dict[str, Any]], camara_id: int) -> Camara:
    """Busca la cámara en la respuesta de `GET /camaras` y falla claro si no está."""
    for camara in camaras:
        if camara.get("id") != camara_id:
            continue
        ultima = camara.get("ultima_lectura") or {}
        return Camara(
            id=camara_id,
            rango_min_c=float(camara["rango_min_c"]),
            rango_max_c=float(camara["rango_max_c"]),
            ultima_temperatura_c=_flotante_opcional(ultima.get("temperatura_c")),
            ultima_humedad_pct=_flotante_opcional(ultima.get("humedad_pct")),
        )

    disponibles = ", ".join(str(camara.get("id")) for camara in camaras) or "ninguna"
    raise ErrorConfiguracion(
        f"La cámara {camara_id} no existe en la API (disponibles: {disponibles})."
    )


def token_de_camara(
    camara_id: int,
    token_manual: str | None = None,
    entorno: Mapping[str, str] | None = None,
) -> str:
    """Resuelve el token del sensor de la cámara, con `--token` o SENSOR_TOKENS.

    Sin `entorno`, lee la configuración compartida (`app.config`), que resuelve
    las variables de entorno y `backend/.env`; el simulador corre desde `backend`.
    """
    sensor_id = SENSORES.get(camara_id)
    if sensor_id is None:
        raise ErrorConfiguracion(f"No hay un sensor asignado a la cámara {camara_id}.")

    if token_manual and token_manual.strip():
        return token_manual.strip()

    try:
        crudo = None if entorno is None else entorno.get("SENSOR_TOKENS", "")
        tokens = leer_sensor_tokens(crudo)
    except ValueError as error:
        raise ErrorConfiguracion(str(error)) from error

    token = tokens.get(sensor_id)
    if not isinstance(token, str) or not token.strip():
        raise ErrorConfiguracion(
            f"No hay token para {sensor_id} en SENSOR_TOKENS; define esa variable "
            f'con la forma {{"{sensor_id}": "..."}} o pasa --token.'
        )
    return token.strip()


def construir_payload(
    camara_id: int,
    sensor_id: str,
    lectura: LecturaSimulada,
    humedad_pct: float,
) -> dict[str, Any]:
    """Arma el cuerpo de `POST /telemetria` con `ts` en ISO 8601 con zona."""
    return {
        "sensor_id": sensor_id,
        "camara_id": camara_id,
        "ts": datetime.now().astimezone().isoformat(),
        "temperatura_c": lectura.temperatura_c,
        "humedad_pct": humedad_pct,
        "puerta_abierta": lectura.puerta_abierta,
    }


def _detalle(respuesta: Respuesta, por_defecto: str) -> str:
    detalle = respuesta.datos.get("detail")
    return str(detalle) if detalle else por_defecto


def _enviar_con_reintentos(
    api: ApiSimulador,
    datos: dict[str, Any],
    token: str,
    dormir: Callable[[float], None],
) -> Respuesta | None:
    """Envía una lectura reintentando fallos transitorios (red, timeout o 5xx).

    Regresa la respuesta definitiva (202 o 4xx) o, si se agotaron los intentos,
    la última respuesta 5xx o None. Nunca propaga `ErrorAPI`.
    """
    respuesta: Respuesta | None = None
    fallo = ""
    for intento in range(1, INTENTOS_POR_LECTURA + 1):
        try:
            respuesta = api.enviar_lectura(datos, token)
        except ErrorAPI as error:
            respuesta = None
            fallo = str(error)
        else:
            if respuesta.status_code < 500:
                return respuesta
            detalle = _detalle(respuesta, "sin detalle")
            fallo = f"el API respondió {respuesta.status_code}: {detalle}"

        if intento < INTENTOS_POR_LECTURA:
            print(
                f"Fallo transitorio al enviar la lectura "
                f"(intento {intento}/{INTENTOS_POR_LECTURA}): {fallo}. Reintentando.",
                file=sys.stderr,
            )
            dormir(ESPERA_REINTENTO_SEGUNDOS)

    print(
        f"Se omite la lectura tras {INTENTOS_POR_LECTURA} intentos: {fallo}",
        file=sys.stderr,
    )
    return respuesta


def _enviar_lecturas(
    args: argparse.Namespace,
    camara: Camara,
    sensor_id: str,
    token: str,
    api: ApiSimulador,
    dormir: Callable[[float], None],
    azar: Callable[[], float],
) -> int:
    anterior = camara.ultima_temperatura_c
    humedad = (
        camara.ultima_humedad_pct
        if camara.ultima_humedad_pct is not None
        else HUMEDAD_POR_DEFECTO
    )
    generadas = 0

    while True:
        lectura = siguiente_lectura(
            args.escenario,
            camara.rango_min_c,
            camara.rango_max_c,
            anterior,
            azar(),
        )
        datos = construir_payload(camara.id, sensor_id, lectura, humedad)
        respuesta = _enviar_con_reintentos(api, datos, token, dormir)

        # La simulación avanza aunque el API no registre esta lectura.
        anterior = lectura.temperatura_c
        generadas += 1

        if respuesta is not None and respuesta.status_code in (401, 403):
            detalle = _detalle(respuesta, "token inválido o sin permiso para esta cámara")
            print(
                f"Error de autenticación ({respuesta.status_code}): {detalle}",
                file=sys.stderr,
            )
            return 1
        if respuesta is not None and 400 <= respuesta.status_code < 500:
            detalle = _detalle(respuesta, "sin detalle")
            print(
                f"El API rechazó la lectura ({respuesta.status_code}): {detalle}",
                file=sys.stderr,
            )
            return 1

        if respuesta is not None and respuesta.status_code == 202:
            estado = respuesta.datos.get("estado_camara", "desconocido")
            print(f"cámara {camara.id} · {lectura.temperatura_c:.1f} °C · {estado}")
        elif respuesta is not None and respuesta.status_code < 500:
            detalle = _detalle(respuesta, "sin detalle")
            print(
                f"El API respondió {respuesta.status_code}: {detalle}; se continúa.",
                file=sys.stderr,
            )

        if args.iteraciones and generadas >= args.iteraciones:
            return 0
        dormir(args.intervalo)


def main(
    argv: Sequence[str] | None = None,
    *,
    cliente: ApiSimulador | None = None,
    dormir: Callable[[float], None] = time.sleep,
    azar: Callable[[], float] = azar_aleatorio,
) -> int:
    """Corre el simulador; regresa el código de salida del proceso."""
    parser = construir_parser()
    args = parser.parse_args(argv)
    if args.intervalo <= 0:
        parser.error("--intervalo debe ser mayor que 0")
    if args.iteraciones < 0:
        parser.error("--iteraciones no puede ser negativo")

    cliente_propio = cliente is None
    api = cliente if cliente is not None else ClienteHTTP(args.api_url)
    try:
        camara = buscar_camara(api.listar_camaras(), args.camara)
        token = token_de_camara(camara.id, args.token)
        sensor_id = SENSORES[camara.id]
        return _enviar_lecturas(args, camara, sensor_id, token, api, dormir, azar)
    except (ErrorConfiguracion, ErrorAPI) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSimulador detenido.", file=sys.stderr)
        return 130
    finally:
        if cliente_propio:
            api.cerrar()
