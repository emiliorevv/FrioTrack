"""Configuración del backend leída de variables de entorno."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_SECRET_POR_DEFECTO = "cambia-esto-en-produccion"
LONGITUD_MINIMA_SECRETO = 32


class Settings(BaseSettings):
    """Valores de configuración; las variables de entorno los sobrescriben."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FríoTrack API"
    # `local` relaja las validaciones; en Render debe ser `produccion`.
    entorno: str = "local"
    escala_tiempo: int = 1
    # Sin default: el runtime exige la cadena de Supabase (ver app/db/session.py).
    database_url: str = ""
    jwt_secret: str = JWT_SECRET_POR_DEFECTO
    jwt_expira_horas: int = 8
    cron_token: str = ""
    sensor_tokens: str = "{}"
    # Obligatoria para cargar el seed (usuarios `jefe` y `gerente`); sin default.
    seed_password: str = ""
    cors_origins: str = "*"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    telefono_jefe: str = ""
    dashboard_url: str = "http://localhost:5173"

    def validar_configuracion(self) -> None:
        """Falla al arrancar si un entorno real conserva el secreto de demo.

        En `local` no valida nada; en cualquier otro entorno (`produccion`) el
        secreto JWT tiene que ser propio y de al menos 32 caracteres.
        """
        if self.entorno.lower() == "local":
            return

        if (
            self.jwt_secret == JWT_SECRET_POR_DEFECTO
            or not self.jwt_secret
            or len(self.jwt_secret) < LONGITUD_MINIMA_SECRETO
        ):
            raise RuntimeError(
                f"Configuración insegura para ENTORNO={self.entorno!r}: define un JWT_SECRET "
                f"propio de al menos {LONGITUD_MINIMA_SECRETO} caracteres (el valor por "
                f"defecto {JWT_SECRET_POR_DEFECTO!r} solo sirve en local)."
            )


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración una sola vez por proceso."""
    return Settings()


def limpiar_cache_settings() -> None:
    """Vacía la caché; las pruebas lo usan tras cambiar variables de entorno."""
    get_settings.cache_clear()
