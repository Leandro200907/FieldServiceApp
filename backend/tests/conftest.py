"""Fixtures compartidas: base real (Postgres local, .env), tenant de prueba aislado y
tokens JWT firmados con el mismo secreto que usa la app.

Cada test que use `tenant_de_prueba` corre contra un tenant nuevo y todo lo que crea
se borra al final (borrado por RLS dentro de tenant_session — solo alcanza lo propio).

La base debe ser explícita (modulo1_test / modulo1_ci); nunca fsm_demo. Ver guardia_base.py.
"""
from __future__ import annotations

import uuid

import pytest

from tests.guardia_base import validar_base_para_pytest


def pytest_configure(config: pytest.Config) -> None:
    validar_base_para_pytest(config)


from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import text

from app.comun.reloj import ahora_utc, congelar_reloj_utc
from app.config import settings
from app.db import tenant_session

# E-106: hoy civil del tenant alineado con OC de prueba (vigencia_hasta ~ 2026-10-05) y
# constantes AHORA de la suite (2026-09-18 … 2026-09-21). 15:00 UTC ≈ mediodía AR.
AHORA_PYTEST_DEFAULT = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reloj_congelado_en_tests(request):
    # Sembrado demo: fechas del script y del tenant demo; no congelar (CI job aparte).
    if request.node.path.name == "test_sembrar_demo.py":
        yield None
        return
    with congelar_reloj_utc(AHORA_PYTEST_DEFAULT):
        yield AHORA_PYTEST_DEFAULT


@pytest.fixture
def reloj_en():
    """Pisa el reloj autouse dentro de un test (p. ej. otro día civil)."""
    return congelar_reloj_utc


@pytest.fixture
def reloj_desde_env():
    """Override puntual vía FSM_TEST_AHORA_UTC (ISO-8601). No lo usa el autouse."""
    import os

    raw = os.environ.get("FSM_TEST_AHORA_UTC")
    if not raw:
        pytest.skip("FSM_TEST_AHORA_UTC no definida")
    instante = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    with congelar_reloj_utc(instante):
        yield instante

ROLES = ("configuracion", "responsable_legajos", "supervisor", "tecnico")

# Orden de borrado: hijos antes que padres (no hay FKs en 0001, pero usuario → tenant sí).
TABLAS_TENANT = [
    "alerta_actualizacion_operadora",
    "movimiento_entrega_operadora",
    "entrega_documento_operadora",
    "operadora_legajo",
    "locacion_oc",
    "tipo_servicio_oc",
    "operadora_documental",
    "notificacion_envio",
    "configuracion_canales",
    "paquete_acceso",
    "paquete_entrega",
    "score_snapshot",
    "archivo_drive",
    "configuracion_drive",
    "alerta_notificacion",
    "alerta_vencimiento",
    "configuracion_alertas",
    "aviso_oc_sin_matriz",
    "plantilla_aviso",
    "refresh_token",
    "asignacion_supervisor",
    "aviso_revaluacion_causa",
    "aviso_revaluacion",
    "aviso_incumplimiento_empresa_causa",
    "aviso_incumplimiento_empresa",
    "politica_evento_procesado",
    "excepcion",
    "constancia_cliente",
    "evaluacion_sujeto_propuesto",
    "evaluacion_habilitacion",
    "requisito_particular",
    "linea_requisito",
    "matriz_requisitos",
    "periodo_custodia",
    "custodia_recurso",
    "documento_soporte",
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
    ahora = ahora_utc()
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


def crear_tenant_de_prueba() -> TenantDePrueba:
    """Tenant nuevo + un usuario por rol. Reutilizable fuera de la fixture (tests que
    necesitan dos tenants a la vez)."""
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
                    "h": "$2b$12$B6psVF.t.UCDfwi1heqT0unV5R.Sh8F.uf/BP5LXjF4UBmmG.O1U2",
                    "r": [rol],
                    "sj": sujeto_tecnico if rol == "tecnico" else None,
                },
            )
    return TenantDePrueba(tenant_id=tenant_id, slug=slug, usuarios=usuarios, sujeto_tecnico=sujeto_tecnico)


def limpiar_tenant(tenant_id: str) -> None:
    with tenant_session(tenant_id) as s:
        for tabla in TABLAS_TENANT:
            s.execute(text(f"DELETE FROM modulo1.{tabla}"))


@pytest.fixture
def tenant_de_prueba() -> TenantDePrueba:
    t = crear_tenant_de_prueba()
    yield t
    limpiar_tenant(t.tenant_id)


@pytest.fixture
def dos_tenants() -> tuple[TenantDePrueba, TenantDePrueba]:
    a, b = crear_tenant_de_prueba(), crear_tenant_de_prueba()
    yield a, b
    limpiar_tenant(a.tenant_id)
    limpiar_tenant(b.tenant_id)


@pytest.fixture
def cliente_api():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def storage(tmp_path, monkeypatch):
    from app.config import settings
    from app.storage.local import StorageLocal

    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    return StorageLocal()

