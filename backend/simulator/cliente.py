"""Cliente HTTP del simulador contra la API de FríoTrack (ver contrato-api.md)."""

from dataclasses import dataclass
from typing import Any

import httpx

TIMEOUT_SEGUNDOS = 10.0


class ErrorAPI(RuntimeError):
    """La API no respondió o lo hizo con un error inesperado."""


@dataclass(frozen=True)
class Respuesta:
    """Lo mínimo que necesita el simulador de una respuesta del API."""

    status_code: int
    datos: dict[str, Any]


def _cuerpo(respuesta: httpx.Response) -> dict[str, Any]:
    """Devuelve el JSON de la respuesta; si no es un objeto, devuelve {}."""
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return {}
    return cuerpo if isinstance(cuerpo, dict) else {}


class ClienteHTTP:
    """Cliente httpx con las dos llamadas que usa el simulador."""

    def __init__(
        self,
        api_url: str,
        timeout: float = TIMEOUT_SEGUNDOS,
        transporte: httpx.BaseTransport | None = None,
    ) -> None:
        self._url_base = api_url.rstrip("/")
        self._cliente = httpx.Client(timeout=timeout, transport=transporte)

    def listar_camaras(self) -> list[dict[str, Any]]:
        """GET /camaras: rangos y última lectura de cada cámara."""
        try:
            respuesta = self._cliente.get(f"{self._url_base}/camaras")
        except httpx.HTTPError as error:
            raise ErrorAPI(f"No se pudo conectar con {self._url_base}: {error}") from error

        if respuesta.status_code != 200:
            raise ErrorAPI(
                f"GET /camaras respondió {respuesta.status_code}: {respuesta.text[:200]}"
            )
        try:
            cuerpo = respuesta.json()
        except ValueError as error:
            raise ErrorAPI("GET /camaras no devolvió JSON válido.") from error
        if not isinstance(cuerpo, list):
            raise ErrorAPI("GET /camaras no devolvió una lista de cámaras.")
        return cuerpo

    def enviar_lectura(self, datos: dict[str, Any], token: str) -> Respuesta:
        """POST /telemetria con el token del sensor en `Authorization`."""
        try:
            respuesta = self._cliente.post(
                f"{self._url_base}/telemetria",
                json=datos,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as error:
            raise ErrorAPI(f"No se pudo enviar la lectura: {error}") from error

        return Respuesta(respuesta.status_code, _cuerpo(respuesta))

    def cerrar(self) -> None:
        """Cierra el pool de conexiones."""
        self._cliente.close()
