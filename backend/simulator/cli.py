"""Simulador de sensores de FríoTrack.

Uso:
    python -m simulator --escenario normal --camara 1 --intervalo 3 --iteraciones 0
"""

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from simulator.cliente import ClienteHTTP, ErrorAPI, Respuesta
from simulator.escenarios import (
    ESCENARIOS,
    LecturaSimulada,
    azar_aleatorio,
    siguiente_lectura,
)

SENSORES_POR_CAMARA = {
    1: "S-PES-01",
    2: "S-CAR-01",
    3: "S-LAC-01",
    4: "S-VER-01",
    5: "S-CON-01",
}
HUMEDAD_POR_DEFECTO = 80.0
API_URL_POR_DEFECTO = "http://127.0.0.1:8000/api"


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


def _tokens_del_entorno(entorno: Mapping[str, str]) -> dict[str, Any]:
    crudo = entorno.get("SENSOR_TOKENS", "")
    try:
        tokens = json.loads(crudo or "{}")
    except json.JSONDecodeError as error:
        raise ErrorConfiguracion(
            "SENSOR_TOKENS no es JSON válido; usa el formato "
            '{"S-PES-01": "token", ...}.'
        ) from error
    if not isinstance(tokens, dict):
        raise ErrorConfiguracion(
            'SENSOR_TOKENS debe ser un objeto JSON con la forma {"S-PES-01": "token", ...}.'
        )
    return tokens


def token_de_camara(
    camara_id: int,
    token_manual: str | None = None,
    entorno: Mapping[str, str] | None = None,
) -> str:
    """Resuelve el token del sensor de la cámara, con `--token` o SENSOR_TOKENS."""
    sensor_id = SENSORES_POR_CAMARA.get(camara_id)
    if sensor_id is None:
        raise ErrorConfiguracion(f"No hay un sensor asignado a la cámara {camara_id}.")

    if token_manual and token_manual.strip():
        return token_manual.strip()

    variables = os.environ if entorno is None else entorno
    token = _tokens_del_entorno(variables).get(sensor_id)
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
    enviadas = 0

    while True:
        lectura = siguiente_lectura(
            args.escenario,
            camara.rango_min_c,
            camara.rango_max_c,
            anterior,
            azar(),
        )
        datos = construir_payload(camara.id, sensor_id, lectura, humedad)
        respuesta = api.enviar_lectura(datos, token)

        if respuesta.status_code in (401, 403):
            detalle = _detalle(respuesta, "token inválido o sin permiso para esta cámara")
            print(
                f"Error de autenticación ({respuesta.status_code}): {detalle}",
                file=sys.stderr,
            )
            return 1
        if respuesta.status_code != 202:
            detalle = _detalle(respuesta, "sin detalle")
            print(
                f"El API respondió {respuesta.status_code}: {detalle}",
                file=sys.stderr,
            )
            return 1

        estado = respuesta.datos.get("estado_camara", "desconocido")
        print(f"cámara {camara.id} · {lectura.temperatura_c:.2f} °C · {estado}")

        anterior = lectura.temperatura_c
        enviadas += 1
        if args.iteraciones and enviadas >= args.iteraciones:
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

    api = cliente if cliente is not None else ClienteHTTP(args.api_url)
    try:
        camara = buscar_camara(api.listar_camaras(), args.camara)
        token = token_de_camara(camara.id, args.token)
        sensor_id = SENSORES_POR_CAMARA[camara.id]
        return _enviar_lecturas(args, camara, sensor_id, token, api, dormir, azar)
    except (ErrorConfiguracion, ErrorAPI) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSimulador detenido.", file=sys.stderr)
        return 130
    finally:
        api.cerrar()
