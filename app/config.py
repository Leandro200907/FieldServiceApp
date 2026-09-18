"""Configuración de la aplicación, leída de variables de entorno.

Sin secretos hardcodeados (nunca, ni siquiera para desarrollo) — ver .env.example.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres — dos URLs distintas a propósito (8.1, decisión 2): el rol de aplicación
    # nunca es owner de las tablas ni corre migraciones. DATABASE_URL_MIGRATIONS es el
    # rol owner, usado solo por Alembic, nunca por el código de la aplicación en runtime.
    database_url: str
    database_url_migrations: str

    # JWT (9.2)
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 30
    jwt_refresh_token_days: int = 14

    # Zona horaria por defecto del tenant (0.3 de especificacion.md) — se sobreescribe
    # por tenant en la tabla de configuración, esto es solo el fallback de arranque.
    tenant_default_timezone: str = "America/Argentina/Buenos_Aires"


settings = Settings()
