"""Configuración del backend leída de variables de entorno."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Valores de configuración; las variables de entorno los sobrescriben."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FríoTrack API"
    escala_tiempo: int = 1
    # Desarrollo usa SQLite; producción la sobrescribe con el Postgres de Supabase.
    database_url: str = "sqlite:///./friotrack.db"
    jwt_secret: str = "cambia-esto-en-produccion"
    jwt_expira_horas: int = 8
    cron_token: str = ""
    sensor_tokens: str = "{}"
    # Contraseña de los usuarios semilla `jefe` y `gerente`.
    seed_password: str = "friotrack-demo"
    cors_origins: str = "*"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    telefono_jefe: str = ""
    dashboard_url: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración una sola vez por proceso."""
    return Settings()


def limpiar_cache_settings() -> None:
    """Vacía la caché; las pruebas lo usan tras cambiar variables de entorno."""
    get_settings.cache_clear()
