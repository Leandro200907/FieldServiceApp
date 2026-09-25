Warning: truncated output (original token count: 8502)
Total output lines: 570

"""Revisión de integración y robustez (sesión 4): cadenas de versiones, invariantes de
agregación, aislamiento entre tenants, concurrencia mínima y contrato HTTP.
"""
from __future__ import annotations

import itertools
import threading
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from tests import apoyo
from sqlalchemy.exc import IntegrityError

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado
from app.auth.alcance import ROLES_CON_TODO_DESCARGA, alcance_de_sujetos, sujeto_en_alcance
from app.auth.identidad import Identidad, Rol
from app.core.orquestacion import evaluar_compromiso
from app.db import tenant_session
from app.modules.legajos import esquemas as esq
from app.modules.legajos import servicio as legajos
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _docs, _ok, _post, _vigentes
from tests.test_orquestacion import (
    armar_escenario,
    decidir,
    clave_de_matriz,
    insertar_definicion,
    insertar_documento,
    insertar_excepcion,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
    requisitos_de,
    sesion,  # noqa: F401
)

AHORA = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _estados(t, persona, req) -> dict[str, str]:
    return {d["documento_id"]: d["estado_version"] for d in _docs(t, persona, req)}


def _assert_a_lo_sumo_un_vigente(t, persona, req):
    assert len(_vigentes(_docs(t, persona, req))) <= 1


def _proponer(c, t, persona, req, desde, hasta) -> str:
    return _ok(_post(c, t, "tecnico", "proponer_documento", {
        "sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": desde, "vigente_hasta": hasta}))["documento_id"]


def _lote(c, t, persona, req, filas: list[tuple[str, str]]) -> tuple[str, list[str]]:
    lote = str(uuid.uuid4())
    r = _ok(_post(c, t, "responsable_legajos", "importar_lote", {"lote_id": lote, "filas": [
        {"sujeto_id": persona, "requisito_definicion_id": re…7502 tokens truncated… # 409 de dominio y detalles con date/UUID serializados (no 500)
    req = _alta_def(c, t, "Apto")
    p = _alta_persona(c, t, "H-1")
    r = c.post("/v1/comandos/alta_de_sujeto", json={"tipo_sujeto": "persona", "identificador_natural": "H-1"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["codigo"] == "conflicto"
    _cargar(c, t, p, req, hasta="2026-06-30")
    r = c.post("/v1/comandos/cargar_documento", json={"sujeto_id": p, "requisito_definicion_id": req,
               "vigente_desde": "2026-12-31", "vigente_hasta": "2026-01-01"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["detalles"] is not None
    # respuestas OK: UUID/date/enum como strings JSON planos
    leg = _ok(c.get("/v1/consultas/legajo", params={"sujeto_id": p}, headers=h))
    doc = leg["documentos"][0]
    assert isinstance(doc["id"], str) and uuid.UUID(doc["id"]) and doc["tipo"] == "documento"
    assert date.fromisoformat(doc["vigente_hasta"]) == date(2026, 6, 30)
    assert doc["estado_confirmacion"] == "verificado"


def test_contrato_http_todas_las_rutas_estan_protegidas(cliente_api):
    """Cada ruta bajo /v1 (salvo salud, login/refresh y la URL prefirmada de storage) exige
    token: sin Authorization responde 401 con envelope, nunca 500 ni 200."""
    paths = cliente_api.get("/openapi.json").json()["paths"]
    publicas = {"/v1/salud/vivo", "/v1/salud/listo", "/v1/auth/login", "/v1/auth/refresh", "/v1/storage/{firma}",
                "/v1/publico/paquete/{token}", "/v1/publico/paquete/{token}/qr.png"}
    assert len(paths) == 91
    for path, ops in paths.items():
        if path in publicas:
            continue
        for metodo in ops:
            url = path.replace("{documento_id}", str(uuid.uuid4()))
            r = cliente_api.post(url, json={}) if metodo == "post" else getattr(cliente_api, metodo)(url)
            assert r.status_code == 401, (metodo, path, r.status_code)
            assert r.json()["error"]["codigo"] == "no_autenticado"

