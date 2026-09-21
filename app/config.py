"""Configuración de la aplicación, leída de variables de entorno.

Sin secretos hardcodeados (nunca, ni siquiera para desarrollo) — ver .env.example.

Archivo de entorno (regla única para API, worker, Alembic y scripts, `archivo_de_entorno()`):
  1. las variables reales del proceso tienen precedencia sobre cualquier archivo;
  2. si `ENV_FILE` está definido, se lee ESE archivo (y sólo ése; si no existe, se
     ignora en silencio y valen únicamente las variables del proceso);
  3. `.env` del directorio de trabajo se lee sólo cuando `ENV_FILE` no fue indicado.
`describir_entorno()` devuelve lo que se puede registrar en un log de arranque: el
archivo elegido, el nombre de la base y el host — nunca contraseñas, secretos ni el DSN
completo.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.entorno import archivo_de_entorno


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=archivo_de_entorno(), extra="ignore")

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

    # Worker: cadencia del loop y umbral de readiness (`/salud/listo` exige un latido
    # global del worker más reciente que este umbral).
    worker_poll_seg: float = 5
    worker_latido_max_seg: int = 120

    # Zona horaria por defecto del tenant (0.3 de especificacion.md) — se sobreescribe
    # por tenant en la tabla de configuración, esto es solo el fallback de arranque.
    tenant_default_timezone: str = "America/Argentina/Buenos_Aires"

    # Nivel del entorno (reauditoría Fase 2 punto 3): sólo gatilla validaciones de arranque
    # más estrictas (hoy: PAQUETE_SECRET obligatorio) — nunca cambia comportamiento de
    # dominio. Default "desarrollo" para no romper ningún entorno existente que no lo fije.
    entorno: str = "desarrollo"

    # Proxies confiables (reauditoría Fase 2 punto 3): IPs/CIDRs separados por coma del
    # balanceador/reverse-proxy real frente a la API. Vacío por defecto — sin esto
    # configurado, `X-Forwarded-For` NUNCA se usa (ver app/comun/red.py); no hay proxy que
    # confiar en un despliegue de instancia única expuesta directo.
    proxies_confiables: str = ""


settings = Settings()


def es_produccion() -> bool:
    return settings.entorno.strip().lower() == "produccion"


def describir_entorno() -> dict[str, str]:
    """Datos NO sensibles del entorno efectivo, para el log de arranque de API y worker."""
    partes = urlsplit(settings.database_url)
    return {
        "env_file": archivo_de_entorno(),
        "base": (partes.path or "/").lstrip("/") or "?",
        "host": partes.hostname or "?",
        "zona_horaria": settings.tenant_default_timezone,
    }
