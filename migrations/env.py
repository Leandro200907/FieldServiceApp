"""Alembic corre siempre con el rol owner (DATABASE_URL_MIGRATIONS), nunca con el rol
de aplicación — 8.1 de modulo1-arquitectura-tecnica.md, decisión 2: "El rol de
migraciones (owner, separado) corre solo desde el pipeline de deploy, nunca desde
código de aplicación." Este archivo es ese pipeline; app/db.py y app/config.py nunca conocen
esta credencial (A-01 de la auditoría).
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class _ConfigMigraciones(BaseSettings):
    """Configuración propia de Alembic: NO usa app.config, que a propósito no conoce
    esta credencial. Lee del entorno (o del .env local de desarrollo; ENV_FILE permite
    apuntar a otro archivo o a uno inexistente)."""

    model_config = SettingsConfigDict(env_file=os.environ.get("ENV_FILE", ".env"), extra="ignore")
    database_url_migrations: str


config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False: si Alembic corre en el mismo proceso que la app (tests,
    # tooling), no debe silenciar los loggers ya creados (modulo1.api, modulo1.worker).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

try:
    _cfg = _ConfigMigraciones()
except Exception as exc:  # pragma: no cover - mensaje explícito para el operador
    raise SystemExit(
        "Falta DATABASE_URL_MIGRATIONS (rol owner). Alembic corre solo desde el job de "
        "despliegue con esa variable; ver scripts/crear_roles.sql y README."
    ) from exc

config.set_main_option("sqlalchemy.url", _cfg.database_url_migrations)

target_metadata = None  # migraciones escritas a mano (SQL explícito), no autogenerate


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
