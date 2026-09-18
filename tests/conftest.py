"""Fixtures compartidas: base real (Postgres local, .env), tenant de prueba aislado y
tokens JWT firmados con el mismo secreto que usa la app.

Cada test que use `tenant_de_prueba` corre contra un tenant nuevo y todo lo que crea
se borra al final (borrado por RLS dentro de tenant_session — solo alcanza lo propio).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import text

from app.config import settings
from app.db import tenant_session

ROLES = ("configuracion", "responsable_legajos", "supervisor", "tecnico")

# Orden de borrado: hijos antes que padres (no hay FKs en 0001, pero usuario → tenant sí).
TABLAS_TENANT = [
    "refresh_token",
    "asignacion_supervisor",
    "excepcion",
    "constancia_cliente",
    "evaluacion_habilitacion",
    "requisito_particular",
    "linea_requisito",
    "matriz_requisitos",
    "periodo_custodia",
    "custodia_recurso",
    "induccion",
    "acreditacion_competencia",
    "documento",
    "oc",
    "lote_importacion",
    "legajo",
    "definicion_requisito",
    "idempotency_keys",
    "outbox_events",
    "event_log",
    "job_queue",
    "usuario",
    "tenant",
]


def token_para(
    tenant_id: str,
    usuario_id: str,
    roles: list[str],
    sujeto_id: str | None = None,
    minutos: int = 30,
) -> str:
    ahora = datetime.now(timezone.utc)
    claims = {
        "sub": usuario_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "sujeto_id": sujeto_id,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos),
        "tipo": "access",
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@dataclass
class TenantDePrueba:
    tenant_id: str
    slug: str
    usuarios: dict[str, str]  # rol -> usuario_id
    sujeto_tecnico: str  # sujeto_id vinculado al usuario técnico

    def token(self, rol: str) -> str:
        sujeto = self.sujeto_tecnico if rol == "tecnico" else None
        return token_para(self.tenant_id, self.usuarios[rol], [rol], sujeto)

    def headers(self, rol: str, idempotency_key: str | None = None) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.token(rol)}"}
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key
        return h


@pytest.fixture
def tenant_de_prueba() -> TenantDePrueba:
    tenant_id = str(uuid.uuid4())
    slug = f"test-{tenant_id[:8]}"
    usuarios: dict[str, str] = {}
    sujeto_tecnico = f"persona_{tenant_id[:8]}"
    with tenant_session(tenant_id) as s:
        s.execute(
            text("INSERT INTO modulo1.tenant (tenant_id, nombre, slug) VALUES (:t, :n, :slug)"),
            {"t": tenant_id, "n": f"Tenant de prueba {slug}", "slug": slug},
        )
        for rol in ROLES:
            uid = str(uuid.uuid4())
            usuarios[rol] = uid
            s.execute(
                text(
                    "INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles, sujeto_id) "
                    "VALUES (:u, :t, :e, :n, :h, :r, :sj)"
                ),
                {
                    "u": uid,
                    "t": tenant_id,
                    "e": f"{rol}@{slug}.test",
                    "n": rol,
                    # hash bcrypt de 'secreto' — solo para tests
                    "h": "$2b$12$C6UzMDM.H6dfI/f/IKcEeO5x0S0m9v8n6k3n4YQ5k6Xy1lM2n3O4a",
                    "r": [rol],
                    "sj": sujeto_tecnico if rol == "tecnico" else None,
                },
            )
    yield TenantDePrueba(tenant_id=tenant_id, slug=slug, usuarios=usuarios, sujeto_tecnico=sujeto_tecnico)
    with tenant_session(tenant_id) as s:
        for tabla in TABLAS_TENANT:
            s.execute(text(f"DELETE FROM modulo1.{tabla}"))


@pytest.fixture
def cliente_api():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
