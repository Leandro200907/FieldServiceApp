"""Conexión a Postgres y contexto de tenant (8.1 de modulo1-arquitectura-tecnica.md).

Decisión cerrada que este módulo implementa al pie de la letra:
  "El middleware setea SET LOCAL app.current_tenant al abrir cada transacción, con un
  único rol de aplicación. El valor del tenant NUNCA se toma de un dato controlado por
  el cliente (no de un header, parámetro o campo del request) — se resuelve siempre a
  partir de la identidad ya autenticada y autorizada de la sesión, y recién con ese
  valor resuelto se abre la transacción y se fija el contexto."

Por eso `tenant_session` no acepta un tenant_id crudo desde una capa de request: lo
llama siempre el dependency de auth (app/auth/dependencies.py) después de validar el
JWT, nunca un router directamente con un valor de query/body.
"""
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# Rol de aplicación — nunca owner, nunca BYPASSRLS (8.1, decisión 2).
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Motor separado para migraciones, con el rol owner — nunca se importa desde código
# de aplicación en runtime, solo desde migrations/env.py.
migrations_engine = create_engine(settings.database_url_migrations, pool_pre_ping=True)


@contextmanager
def tenant_session(tenant_id: str) -> Iterator[Session]:
    """Abre una transacción con `app.current_tenant` fijado para RLS.

    `tenant_id` debe venir siempre de la identidad ya autenticada (ver docstring del
    módulo) — este contexto no valida esto por sí mismo, es responsabilidad de quien
    lo llama. Usa SET LOCAL (no SET) porque el pool corre en modo transacción (8.1):
    SET persistiría el valor más allá de esta transacción y podría filtrarse a la
    siguiente conexión lógica que reutilice la misma conexión física del pool.
    """
    session = SessionLocal()
    try:
        # set_config(..., is_local=true) es exactamente SET LOCAL, pero admite parámetro
        # bind (SET LOCAL no acepta $1 en Postgres) — así el tenant_id nunca se interpola
        # en el SQL como string.
        session.execute(
            text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def platform_session() -> Iterator[Session]:
    """Sesión sin contexto de tenant — solo para datos del schema `plataforma`
    (catálogo global de industria, 8.1 decisión 4). El rol de aplicación solo tiene
    GRANT SELECT ahí; la escritura queda para un rol de administración aparte que no
    vive en este módulo.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
