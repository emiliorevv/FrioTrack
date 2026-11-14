"""Script de ataque para la demo del módulo de seguridad.

Manda lecturas con tokens de sensor falsos desde una IP loopback alterna
(`127.0.0.2` por defecto) para disparar la regla de fuerza bruta sin bloquear
la IP del dashboard ni del simulador. Solo usa la biblioteca estándar y no
importa el detector ni psycopg: es un cliente independiente de la API.

En Linux, cualquier 127.0.0.x ya existe en el loopback. En macOS solo está
`127.0.0.1`, así que antes de la demo hay que agregar la IP una vez:

    sudo ifconfig lo0 alias 127.0.0.2 up
"""

from __future__ import annotations

import argparse
import errno
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPConnection, HTTPException
from time import sleep
from urllib.parse import SplitResult, urlsplit

API_URL_POR_DEFECTO = "http://127.0.0.1:8000/api"
IP_LOCAL_POR_DEFECTO = "127.0.0.2"
SENSOR_ID = "S-PES-01"
CAMARA_ID = 1
TIEMPO_ESPERA_SEG = 5
PREFIJO_TOKEN = "token-falso"


@dataclass(frozen=True)
class Peticion:
    """Una petición HTTP ya armada, sin conexión de red."""

    metodo: str
    ruta: str
    headers: dict[str, str]
    cuerpo: bytes


def construir_peticion(indice: int) -> Peticion:
    """Arma el POST con el token falso número `indice` y una lectura válida."""
    cuerpo = {
        "sensor_id": SENSOR_ID,
        "camara_id": CAMARA_ID,
        "ts": datetime.now(UTC).isoformat(),
        "temperatura_c": 1.4,
        "humedad_pct": 88,
        "puerta_abierta": False,
    }
    return Peticion(
        metodo="POST",
        ruta="/telemetria",
        headers={
            "Authorization": f"Bearer {PREFIJO_TOKEN}-{indice}",
            "Content-Type": "application/json",
        },
        cuerpo=json.dumps(cuerpo).encode("utf-8"),
    )


def _partes(api_url: str) -> SplitResult:
    partes = urlsplit(api_url)
    if partes.scheme != "http" or not partes.hostname:
        raise ValueError(f"--api-url debe ser http con host válido: {api_url!r}")
    return partes


def enviar(api_url: str, ip_local: str, peticion: Peticion) -> tuple[int, str]:
    """Envía una petición desde `ip_local` y regresa `(status, cuerpo)`."""
    partes = _partes(api_url)
    puerto = partes.port or 80
    ruta = f"{partes.path.rstrip('/')}{peticion.ruta}"
    conexion = HTTPConnection(
        partes.hostname,
        puerto,
        timeout=TIEMPO_ESPERA_SEG,
        source_address=(ip_local, 0),
    )
    try:
        conexion.request(
            peticion.metodo,
            ruta,
            body=peticion.cuerpo,
            headers=peticion.headers,
        )
        respuesta = conexion.getresponse()
        return respuesta.status, respuesta.read().decode("utf-8", errors="replace")
    finally:
        conexion.close()


def _enviar_e_imprimir(api_url: str, ip_local: str, indice: int) -> bool:
    """Manda una petición e imprime el status; regresa False si falló la red."""
    peticion = construir_peticion(indice)
    try:
        status, cuerpo = enviar(api_url, ip_local, peticion)
    except OSError as error:
        print(f"{indice:02d} error de red: {error}")
        if error.errno == errno.EADDRNOTAVAIL:
            print(
                f"No se puede usar {ip_local} como IP de origen. En macOS hay que "
                f"agregarla al loopback (una vez por arranque):\n"
                f"  sudo ifconfig lo0 alias {ip_local} up"
            )
        return False
    except HTTPException as error:
        print(f"{indice:02d} error de red: {error}")
        return False
    recorte = f" {cuerpo[:120]}" if cuerpo else ""
    print(f"{indice:02d} {peticion.metodo} {peticion.ruta} -> {status}{recorte}")
    return True


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manda tokens falsos a /api/telemetria desde una IP loopback alterna "
            "para disparar la regla de fuerza bruta del detector SIEM."
        )
    )
    parser.add_argument("--api-url", default=API_URL_POR_DEFECTO, help="base de la API")
    parser.add_argument("--intentos", type=int, default=15, help="peticiones con token falso")
    parser.add_argument(
        "--ip-local",
        default=IP_LOCAL_POR_DEFECTO,
        help=(
            "IP de origen en loopback; 127.0.0.2 evita bloquear el dashboard "
            "(en macOS requiere `sudo ifconfig lo0 alias 127.0.0.2 up`)"
        ),
    )
    parser.add_argument(
        "--espera",
        type=int,
        default=0,
        metavar="SEGUNDOS",
        help=(
            "si es mayor que 0, espera y manda una petición más para ver el 403 "
            "del bloqueo (el middleware refresca la caché cada 15 s)"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    if args.intentos < 1:
        parser.error("--intentos debe ser al menos 1")
    if args.espera < 0:
        parser.error("--espera no puede ser negativa")
    try:
        _partes(args.api_url)
    except ValueError as error:
        parser.error(str(error))

    print(f"Ataque desde {args.ip_local} contra {args.api_url}: {args.intentos} tokens falsos")
    for indice in range(1, args.intentos + 1):
        if not _enviar_e_imprimir(args.api_url, args.ip_local, indice):
            return 1

    if args.espera > 0:
        print(f"Esperando {args.espera} s para que el detector bloquee la IP...")
        sleep(args.espera)
        if not _enviar_e_imprimir(args.api_url, args.ip_local, args.intentos + 1):
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
