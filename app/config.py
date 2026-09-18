"""Configuración de la aplicación, leída de variables de entorno.

Sin secretos hardcodeados (nunca, ni siquiera para desarrollo) — ver .env.example.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres — SOLO la URL del rol de aplicación (8.1, decisión 2). La credencial del
    # owner (DATABASE_URL_MIGRATIONS) no existe en esta configuración a propósito: la lee
    # únicamente migrations/env.py desde el entorno del job de despliegue. Si la API o
    # el worker la necesitaran, una toma del proceso anularía la barrera de RLS (A-01).
    database_url: str

    # JWT (9.2)
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 30
    jwt_refresh_token_days: int = 14

    # Storage de evidencia (8.5). Secreto de firma propio, distinto del JWT (A-02).
    storage_secret: str
    storage_backend: str = "local"
    storage_local_dir: str = "./storage_local"
    storage_local_base_url: str = "/v1/storage"
    storage_max_bytes: int = 25 * 1024 * 1024  # tope por archivo de evidencia

    # Zona horaria por defecto del tenant (0.3 de especificacion.md) — se sobreescribe
    # por tenant en la tabla de configuración, esto es solo el fallback de arranque.
    tenant_default_timezone: str = "America/Argentina/Buenos_Aires"


settings = Settings()
