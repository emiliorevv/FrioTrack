"""Configuración del backend leída de variables de entorno."""

import json
import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_SECRET_POR_DEFECTO = "cambia-esto-en-produccion"
SEED_PASSWORD_DEMO = "friotrack-demo"
LONGITUD_MINIMA_SECRETO = 32
# Mismos IDs que app/db/seed.py; se duplican aquí para no crear un ciclo de imports.
SENSORES_ESPERADOS = ("S-PES-01", "S-CAR-01", "S-LAC-01", "S-VER-01", "S-CON-01")


class Settings(BaseSettings):
    """Valores de configuración; las variables de entorno los sobrescriben."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FríoTrack API"
    # `local` relaja las validaciones; Render se detecta además con RENDER=true.
    entorno: str = "local"
    escala_tiempo: int = Field(default=1, ge=1)
    # Sin default: el runtime exige la cadena de Supabase (ver app/db/session.py).
    database_url: str = ""
    jwt_secret: str = JWT_SECRET_POR_DEFECTO
    jwt_expira_horas: int = 8
    cron_token: str = ""
    sensor_tokens: str = "{}"
    # Obligatoria para cargar el seed (usuarios `jefe` y `gerente`); sin default.
    seed_password: str = ""
    cors_origins: str = "*"
    # Con False el middleware de acceso solo imprime en stdout: no consulta
    # `ips_bloqueadas` ni escribe en `logs_acceso` (lo usan las pruebas).
    middleware_acceso_db: bool = True
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    telefono_jefe: str = ""
    dashboard_url: str = "http://localhost:5173"

    def es_produccion(self) -> bool:
        """Detecta producción aunque falte ENTORNO: Render define RENDER=true."""
        return self.entorno.lower() != "local" or os.getenv("RENDER", "").lower() == "true"

    def validar_configuracion(self) -> None:
        """Falla al arrancar si producción conserva valores de demo.

        En `local` no valida nada. En producción (`ENTORNO` distinto de `local` o
        `RENDER=true`, como en Render) exige JWT_SECRET fuerte, CRON_TOKEN,
        SEED_PASSWORD propia y un token no vacío para cada sensor.
        """
        if not self.es_produccion():
            return

        if (
            self.jwt_secret == JWT_SECRET_POR_DEFECTO
            or not self.jwt_secret
            or len(self.jwt_secret) < LONGITUD_MINIMA_SECRETO
        ):
            raise RuntimeError(
                f"Configuración insegura en producción (ENTORNO={self.entorno!r}): define "
                f"un JWT_SECRET propio de al menos {LONGITUD_MINIMA_SECRETO} caracteres "
                f"(el valor por defecto {JWT_SECRET_POR_DEFECTO!r} solo sirve en local)."
            )

        if not self.cron_token:
            raise RuntimeError(
                "Falta CRON_TOKEN: el simulador y el Worker de Cloudflare lo usan para "
                "disparar los ticks; defínelo también en producción."
            )

        if not self.seed_password or self.seed_password == SEED_PASSWORD_DEMO:
            raise RuntimeError(
                "Configuración insegura: define una SEED_PASSWORD propia; el valor "
                f"{SEED_PASSWORD_DEMO!r} solo sirve en local."
            )

        self._validar_sensor_tokens()

    def _validar_sensor_tokens(self) -> None:
        """Comprueba que SENSOR_TOKENS sea un objeto JSON con los cinco sensores."""
        try:
            tokens = leer_sensor_tokens(self.sensor_tokens)
        except ValueError as error:
            raise RuntimeError(str(error)) from error

        faltantes = []
        for sensor_id in SENSORES_ESPERADOS:
            token = tokens.get(sensor_id)
            if not isinstance(token, str) or not token.strip():
                faltantes.append(sensor_id)
        if faltantes:
            raise RuntimeError(
                f"Faltan tokens de sensor en SENSOR_TOKENS: {', '.join(faltantes)}. "
                "Configura un token no vacío para cada sensor."
            )


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración una sola vez por proceso."""
    return Settings()


def leer_sensor_tokens(valor: str | None = None) -> dict[str, str]:
    """Parsea el JSON de SENSOR_TOKENS y valida su forma.

    Sin argumento usa `get_settings().sensor_tokens`, que resuelve las variables
    de entorno y `backend/.env`; con un valor explícito parsea ese texto. Lanza
    `ValueError` con un mensaje accionable si no es un objeto de tokens de texto.
    """
    crudo = get_settings().sensor_tokens if valor is None else valor
    try:
        tokens = json.loads(crudo or "{}")
    except json.JSONDecodeError as error:
        raise ValueError(
            "SENSOR_TOKENS no es JSON válido; usa el formato "
            '{"S-PES-01": "token", ...}.'
        ) from error
    if not isinstance(tokens, dict):
        raise ValueError(
            'SENSOR_TOKENS debe ser un objeto JSON con la forma {"S-PES-01": "token", ...}.'
        )
    if not all(isinstance(token, str) for token in tokens.values()):
        raise ValueError(
            'SENSOR_TOKENS debe tener tokens de texto: {"S-PES-01": "token", ...}.'
        )
    return tokens


def limpiar_cache_settings() -> None:
    """Vacía la caché; las pruebas lo usan tras cambiar variables de entorno."""
    get_settings.cache_clear()
