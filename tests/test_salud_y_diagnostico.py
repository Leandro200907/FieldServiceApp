"""Salud (liveness / readiness) y diagnóstico de errores internos (request_id, logs).

Readiness prueba tres fallas: base caída, migración atrasada y storage no disponible.
Los 500 se registran con stack trace y request_id, y al cliente le llega un mensaje
genérico; ni tokens ni cuerpos aparecen en el log."""
from __future__ import annotations

import logging
import os
import socket
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api import salud
from app.db import platform_session
from app.version import MIGRACION_HEAD
from app.worker.procesos_reloj import latir

T0 = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
TODO_OK = {"db": "ok", "migracion": "ok", "storage": "ok", "worker": "ok"}


def _latido_worker(ultimo_ok: datetime | None) -> None:
    """Deja el latido global del worker en el instante dado (None = nunca latió)."""
    with platform_session() as s:
        s.execute(text("DELETE FROM modulo1.latido_proceso WHERE nombre = 'worker' AND tenant_id IS NULL"))
        if ultimo_ok is not None:
            latir(s, "worker", None, True, {"tenants": 0})
            s.execute(text("UPDATE modulo1.latido_proceso SET ultimo_ok = :u WHERE nombre = 'worker' AND tenant_id IS NULL"), {"u": ultimo_ok})


@pytest.fixture
def worker_vivo():
    _latido_worker(T0)
    yield


# --------------------------------------------------------------------------- liveness / readiness


def test_vivo_no_toca_la_base(cliente_api, monkeypatch):
    def _explota():
        raise AssertionError("liveness no debe abrir sesión")
    monkeypatch.setattr(salud, "platform_session", _explota)
    r = cliente_api.get("/v1/salud/vivo")
    assert r.status_code == 200 and r.json()["ok"] is True and "version" in r.json()


def test_listo_ok_con_base_migrada_storage_y_worker(cliente_api, worker_vivo, monkeypatch):
    monkeypatch.setattr(salud, "ahora_utc", lambda: T0 + timedelta(seconds=30))
    r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "version": r.json()["version"], "chequeos": TODO_OK}


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
    assert r.json()["chequeos"]["worker"] == "no_disponible"
    _sin_secretos(r.text)
    assert "secreto@db" not in caplog.text          # el log tampoco lleva el DSN


def test_listo_con_migracion_atrasada_503(cliente_api, monkeypatch, worker_vivo):
    monkeypatch.setattr(salud, "ahora_utc", lambda: T0)
    monkeypatch.setattr(salud, "MIGRACION_HEAD", "9999_futura")
    r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 503 and r.json()["chequeos"] == {**TODO_OK, "migracion": "atrasada"}
    monkeypatch.setattr(salud, "MIGRACION_HEAD", "0001_initial_schema")
    r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 503 and r.json()["chequeos"]["migracion"] == "adelantada"
    _sin_secretos(r.text)


def test_listo_con_storage_no_disponible_503(cliente_api, monkeypatch, tmp_path, worker_vivo):
    monkeypatch.setattr(salud, "ahora_utc", lambda: T0)

    class _Roto:
        def disponible(self):
            raise OSError("disco lleno en C:\\ruta\\interna")
    monkeypatch.setattr(salud, "obtener_storage", lambda: _Roto())
    r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 503 and r.json()["chequeos"] == {**TODO_OK, "storage": "no_disponible"}
    _sin_secretos(r.text)

    class _NoEscribe:
        def disponible(self):
            return False
    monkeypatch.setattr(salud, "obtener_storage", lambda: _NoEscribe())
    assert cliente_api.get("/v1/salud/listo").json()["chequeos"]["storage"] == "no_disponible"


# --------------------------------------------------------------------------- readiness del worker (reloj controlado)


def test_worker_sin_latido_no_listo(cliente_api, monkeypatch):
    _latido_worker(None)
    monkeypatch.setattr(salud, "ahora_utc", lambda: T0)
    r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 503 and r.json()["chequeos"] == {**TODO_OK, "worker": "sin_latido"}
    _sin_secretos(r.text)


def test_worker_latido_reciente_ok_y_vencido_no_listo_segun_umbral(cliente_api, monkeypatch):
    _latido_worker(T0)
    monkeypatch.setattr(salud.settings, "worker_latido_max_seg", 120)
    # justo dentro del umbral: ok; un segundo después del umbral: vencido
    monkeypatch.setattr(salud, "ahora_utc", lambda: T0 + timedelta(seconds=120))
    assert cliente_api.get("/v1/salud/listo").json()["chequeos"]["worker"] == "ok"
    monkeypatch.setattr(salud, "ahora_utc", lambda: T0 + timedelta(seconds=121))
    r = cliente_api.get("/v1/salud/listo")
    assert r.status_code == 503 and r.json()["chequeos"] == {**TODO_OK, "worker": "vencido"}
    # umbral configurable: con 600 s el mismo latido vuelve a estar ok
    monkeypatch.setattr(salud.settings, "worker_latido_max_seg", 600)
    assert cliente_api.get("/v1/salud/listo").status_code == 200
    # y un latido nuevo (worker activo) lo repone con el umbral chico
    monkeypatch.setattr(salud.settings, "worker_latido_max_seg", 120)
    _latido_worker(T0 + timedelta(seconds=100))
    assert cliente_api.get("/v1/salud/listo").json()["chequeos"]["worker"] == "ok"


def test_chequeo_worker_funcion_pura_con_reloj_y_umbral():
    _latido_worker(T0)
    assert salud._chequeo_worker(ahora=T0 + timedelta(seconds=59), umbral_seg=60) == "ok"
    assert salud._chequeo_worker(ahora=T0 + timedelta(seconds=61), umbral_seg=60) == "vencido"
    _latido_worker(None)
    assert salud._chequeo_worker(ahora=T0, umbral_seg=60) == "sin_latido"


def test_una_vuelta_real_del_worker_deja_listo_al_worker(cliente_api):
    from app.worker import main as worker_main
    from app.worker.outbox import PublicadorEnMemoria

    class _Storage:
        def clave_para(self, *a): return "x"
        def existe(self, c): return False
        def inspeccionar(self, c): return None
        def borrar(self, c): return True
        def disponible(self): return True

    _latido_worker(None)
    assert cliente_api.get("/v1/salud/listo").json()["chequeos"]["worker"] == "sin_latido"
    worker_main.correr_una_vuelta(_Storage(), PublicadorEnMemoria())
    assert cliente_api.get("/v1/salud/listo").json()["chequeos"]["worker"] == "ok"


# --------------------------------------------------------------------------- salud pública, sin JWT y sin fugas


def test_salud_es_publica_y_solo_devuelve_estados_cerrados(cliente_api, worker_vivo, monkeypatch):
    monkeypatch.setattr(salud, "ahora_utc", lambda: T0)
    vivo = cliente_api.get("/v1/salud/vivo")             # sin Authorization
    listo = cliente_api.get("/v1/salud/listo")
    assert vivo.status_code == 200 and set(vivo.json()) == {"ok", "version"}
    assert listo.status_code in (200, 503) and set(listo.json()) == {"ok", "version", "chequeos"}
    assert set(listo.json()["chequeos"]) == {"db", "migracion", "storage", "worker"}
    cerrados = {"ok", "no_disponible", "atrasada", "adelantada", "desconocida", "sin_latido", "vencido"}
    assert set(listo.json()["chequeos"].values()) <= cerrados
    for texto in (vivo.text, listo.text):
        _sin_secretos(texto)
        assert socket.gethostname() not in texto and str(os.getpid()) not in texto
    # con un token inválido tampoco cambia nada (no se evalúa)
    assert cliente_api.get("/v1/salud/listo", headers={"Authorization": "Bearer basura"}).status_code in (200, 503)


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
