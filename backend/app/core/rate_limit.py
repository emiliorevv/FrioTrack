"""Limitador en memoria de intentos de login por IP."""

from __future__ import annotations

from collections.abc import Callable
from math import ceil
from threading import Lock
from time import monotonic

LIMITE_INTENTOS_LOGIN = 10
VENTANA_INTENTOS_LOGIN_SEG = 300
MAX_CLAVES = 4096


class LimitadorIntentos:
    """Ventana deslizante por clave, segura entre hilos y con reloj inyectable.

    Cada llamada a `permitir` cuenta un intento. Al llegar al máximo devuelve
    los segundos que faltan para que el intento más viejo salga de la ventana;
    la API lo usa como `Retry-After`. La purga evita que IPs viejas crezcan sin
    límite en memoria.
    """

    def __init__(
        self,
        maximo: int = LIMITE_INTENTOS_LOGIN,
        ventana_seg: float = VENTANA_INTENTOS_LOGIN_SEG,
        reloj: Callable[[], float] = monotonic,
    ) -> None:
        self._maximo = maximo
        self._ventana_seg = ventana_seg
        self._reloj = reloj
        self._intentos: dict[str, list[float]] = {}
        self._lock = Lock()

    def permitir(self, clave: str) -> int:
        """Registra un intento; regresa 0 o los segundos de espera (mínimo 1)."""
        ahora = self._reloj()
        with self._lock:
            self._purgar(ahora)
            intentos = self._vigentes(clave, ahora)
            if len(intentos) >= self._maximo:
                self._intentos[clave] = intentos
                return max(1, ceil(self._ventana_seg - (ahora - intentos[0])))
            intentos.append(ahora)
            self._intentos[clave] = intentos
            return 0

    def limpiar(self, clave: str) -> None:
        """Olvida los intentos de una clave; el login exitoso lo usa al entrar."""
        with self._lock:
            self._intentos.pop(clave, None)

    def reiniciar(self) -> None:
        """Vacía todo el estado; lo usan las pruebas."""
        with self._lock:
            self._intentos.clear()

    def _vigentes(self, clave: str, ahora: float) -> list[float]:
        return [
            instante
            for instante in self._intentos.get(clave, [])
            if ahora - instante < self._ventana_seg
        ]

    def _purgar(self, ahora: float) -> None:
        for clave in [clave for clave in self._intentos if not self._vigentes(clave, ahora)]:
            del self._intentos[clave]
        # Si muchas IPs distintas intentan en pocos segundos, mejor empezar de
        # cero que dejar la memoria crecer sin tope.
        if len(self._intentos) >= MAX_CLAVES:
            self._intentos.clear()
