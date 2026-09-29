"""Drive: importación atómica y validación de archivo antes de crear versión (ALTO-2)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.db import tenant_session
from app.modules.drive.proveedor import ArchivoRemoto, ProveedorEnMemoria
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post


class _Storage:
    def __init__(self, tmp):
        from app.storage.local import StorageLocal
        self.real = StorageLocal(directorio=tmp, secreto="s" * 32)

    def __getattr__(self, n):
        return getattr(self.real, n)


def _remoto(id_, nombre, mime="application/pdf", h=None):
    return ArchivoRemoto(id_, nombre, mime, datetime(2026, 9, 1, tzinfo=timezone.utc), h or f"h-{id_}", 100)


def _habilitar_drive(cliente_api, t):
    _ok(_post(cliente_api, t, "configuracion", "configurar_drive", {"habilitado": True, "carpeta_id": "carpeta-1"}))


def test_pdf_vacio_no_pisa_version_verificada_vigente(cliente_api, tenant_de_prueba, tmp_path, monkeypatch):
    from app.modules import capacidades_router as cr

    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    p = _alta_persona(cliente_api, t, "DNI 9", sujeto_id="persona_v1_ok")
    vigente = _cargar(cliente_api, t, p, req, desde="2026-01-01", hasta="2027-06-30")
    with tenant_session(t.tenant_id) as s:
        s.execute(text(
            "UPDATE modulo1.documento SET estado_confirmacion = 'verificado', archivo_estado = 'confirmado', "
            "checksum_archivo = 'ok', archivo_bytes = 1 WHERE documento_id = :d"
        ), {"d": vigente["documento_id"]})
    prov = ProveedorEnMemoria(
        carpetas={"carpeta-1": [_remoto("vac", "persona_v1_ok__Apto_medico__2027-07-01.pdf", h="hash-vacio")]},
        contenidos={"vac": b""},
    )
    monkeypatch.setattr(cr, "_proveedor_drive", lambda: prov)
    monkeypatch.setattr(cr, "_storage", lambda: _Storage(tmp_path))
    _habilitar_drive(cliente_api, t)
    r = _post(cliente_api, t, "responsable_legajos", "escanear_drive", {})
    assert r.status_code == 200, r.text
    assert r.json()["importados"] == 0 and r.json()["bandeja"] == 1
    with tenant_session(t.tenant_id) as s:
        filas = s.execute(text(
            "SELECT documento_id::text, estado_version, estado_confirmacion FROM modulo1.documento "
            "WHERE tenant_id = :t AND sujeto_id = :s ORDER BY version"
        ), {"t": t.tenant_id, "s": p}).all()
    assert len(filas) == 1
    assert filas[0][0] == vigente["documento_id"] and filas[0][1] == "vigente" and filas[0][2] == "verificado"


def test_archivo_grande_no_frena_escaneo_y_avanza_ultimo_escaneo(cliente_api, tenant_de_prueba, tmp_path, monkeypatch):
    from app.config import settings
    from app.modules import capacidades_router as cr

    t = tenant_de_prueba
    _alta_def(cliente_api, t, "Apto médico")
    _alta_persona(cliente_api, t, "DNI 10", sujeto_id="persona_ok")
    monkeypatch.setattr(settings, "storage_max_bytes", 80)
    prov = ProveedorEnMemoria(
        carpetas={"carpeta-1": [
            _remoto("grande", "persona_ok__Apto_medico__2027-06-30.pdf", h="h-grande"),
            _remoto("chico", "persona_ok__Apto_medico__2027-07-01__2026-07-01.pdf", h="h-chico"),
        ]},
        contenidos={
            "grande": b"%PDF-1.4 " + b"x" * 200,
            "chico": b"%PDF-1.4 ok chico",
        },
    )
    monkeypatch.setattr(cr, "_proveedor_drive", lambda: prov)
    monkeypatch.setattr(cr, "_storage", lambda: _Storage(tmp_path))
    _habilitar_drive(cliente_api, t)
    r = _ok(_post(cliente_api, t, "responsable_legajos", "escanear_drive", {}))
    assert (r["importados"], r["bandeja"], r["vistos"]) == (1, 1, 2)
    band = cliente_api.get("/v1/consultas/bandeja_drive", headers=t.headers("responsable_legajos")).json()
    assert any("archivo_demasiado_grande" in (i.get("motivo") or "") for i in band["items"])
    cfg = cliente_api.get("/v1/consultas/configuracion_drive", headers=t.headers("responsable_legajos")).json()
    assert cfg["ultimo_escaneo_en"] is not None and cfg["ultimo_escaneo_resultado"]["vistos"] == 2
