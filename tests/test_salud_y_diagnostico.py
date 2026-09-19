"""Salud (liveness / readiness) y diagnóstico de errores internos (request_id, logs).

Readiness prueba tres fallas: base caída, migración atrasada y storage no disponible.
Los 500 se registran con stack trace y request_id, y al cliente le llega un mensaje
genérico; ni tokens ni cuerpos aparecen en el log."""
from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest
from sqlalchemy.exc import OperationalError

from app.api import salud
from app.version import MIGRACION_HEAD


# --------------------------------------------------------------------------- liveness / readiness


def test_vivo_no_toca_la_base(cliente_api, monkeypatch):
    def _explota():
        raise AssertionError("liveness no debe abrir sesión")
    monkeypatch.setattr(salud, "platform_session", _explota)
    r = cliente_api.get("/v1/salud/vivo")
    assert r.status_code == 200 and r.json()["ok"] is True and "version" in r.json()


def test_listo_ok_con_base_migrada_y_storage(cliente_api):
    r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "version": r.json()["version"], "chequeos": {"db": "ok", "migracion": "ok", "storage": "ok"}}


def _sin_secretos(texto: str) -> None:
    from app.config import settings
    assert "postgresql" not in texto and settings.storage_secret not in texto and settings.jwt_secret not in texto
    assert "Traceback" not in texto and "OperationalError" not in texto and "/" not in texto.replace("/v1", "")


def test_listo_con_base_caida_503_sin_revelar_dsn(cliente_api, monkeypatch, caplog):
    @contextmanager
    def _caida():
        raise OperationalError("connection refused host=postgresql://modulo1_app:secreto@db:5432/x", None, Exception("x"))
        yield
    monkeypatch.setattr(salud, "platform_session", _caida)
    with caplog.at_level(logging.WARNING):
        r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 503
    assert r.json()["ok"] is False and r.json()["chequeos"]["db"] == "no_disponible" and r.json()["chequeos"]["migracion"] == "desconocida"
    _sin_secretos(r.text)
    assert "secreto@db" not in caplog.text          # el log tampoco lleva el DSN


def test_listo_con_migracion_atrasada_503(cliente_api, monkeypatch):
    monkeypatch.setattr(salud, "MIGRACION_HEAD", "9999_futura")
    r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 503 and r.json()["chequeos"] == {"db": "ok", "migracion": "atrasada", "storage": "ok"}
    monkeypatch.setattr(salud, "MIGRACION_HEAD", "0001_initial_schema")
    r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 503 and r.json()["chequeos"]["migracion"] == "adelantada"
    _sin_secretos(r.text)


def test_listo_con_storage_no_disponible_503(cliente_api, monkeypatch, tmp_path):
    class _Roto:
        def disponible(self):
            raise OSError("disco lleno en C:\\ruta\\interna")
    monkeypatch.setattr(salud, "obtener_storage", lambda: _Roto())
    r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 503 and r.json()["chequeos"] == {"db": "ok", "migracion": "ok", "storage": "no_disponible"}
    _sin_secretos(r.text)

    class _NoEscribe:
        def disponible(self):
            return False
    monkeypatch.setattr(salud, "obtener_storage", lambda: _NoEscribe())
    assert cliente_api.get("/v1/salud/listo").json()["chequeos"]["storage"] == "no_disponible"


def test_storage_local_disponible_real(tmp_path):
    from app.storage.local import StorageLocal
    assert StorageLocal(directorio=tmp_path / "nuevo", secreto="s" * 32).disponible() is True
    archivo = tmp_path / "archivo"
    archivo.write_text("x")
    assert StorageLocal(directorio=archivo, secreto="s" * 32).disponible() is False  # un archivo no es un directorio


def test_head_esperado_coincide_con_el_head_real_de_alembic():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    assert heads == [MIGRACION_HEAD]


# --------------------------------------------------------------------------- 500 con request_id


@pytest.fixture
def ruta_que_explota():
    from app.main import app

    @app.get("/v1/_test/explota")
    def _explota():
        raise RuntimeError("detalle interno con ruta C:\\secreta\\archivo.py y token=abc")

    yield
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/v1/_test/explota"]


def test_500_generico_con_request_id_y_stack_trace_en_el_log(cliente_api, tenant_de_prueba, ruta_que_explota, caplog):
    with caplog.at_level(logging.ERROR, logger="modulo1.api"):
        r = cliente_api.get("/v1/_test/explota", headers={**tenant_de_prueba.headers("supervisor"), "X-Request-ID": "corr-123"})
    assert r.status_code == 500
    cuerpo = r.json()["error"]
    assert cuerpo == {"codigo": "error_interno", "mensaje": "Error interno; informá el request_id", "detalles": None, "request_id": "corr-123"}
    assert r.headers["X-Request-ID"] == "corr-123"
    assert "detalle interno" not in r.text and "secreta" not in r.text
    # Log: stack trace + request_id + método/ruta; sin el token ni headers.
    registro = next(rec for rec in caplog.records if rec.levelno == logging.ERROR)
    assert "request_id=corr-123" in registro.getMessage() and "GET /v1/_test/explota" in registro.getMessage()
    assert registro.exc_info and "RuntimeError" in caplog.text and 'raise RuntimeError' in caplog.text
    token = tenant_de_prueba.headers("supervisor")["Authorization"].split()[1]
    assert token not in caplog.text and "Bearer" not in caplog.text


def test_500_sin_header_genera_request_id_propio(cliente_api, ruta_que_explota):
    r = cliente_api.get("/v1/_test/explota")
    assert r.status_code == 500
    rid = r.json()["error"]["request_id"]
    assert len(rid) == 36 and r.headers["X-Request-ID"] == rid


def test_toda_respuesta_lleva_request_id(cliente_api):
    r = cliente_api.get("/v1/salud/vivo", headers={"X-Request-ID": "abc"})
    assert r.headers["X-Request-ID"] == "abc"
    r = cliente_api.get("/v1/salud/vivo")
    assert len(r.headers["X-Request-ID"]) == 36


def test_422_no_registra_ni_devuelve_el_cuerpo(cliente_api, tenant_de_prueba, caplog):
    with caplog.at_level(logging.DEBUG):
        r = cliente_api.post("/v1/comandos/evaluar_habilitacion", json={"commitment_id": "OC-SECRETA-XYZ"},
                             headers=tenant_de_prueba.headers("responsable_legajos"))
    assert r.status_code == 422
    assert "OC-SECRETA-XYZ" not in r.text and "OC-SECRETA-XYZ" not in caplog.text
