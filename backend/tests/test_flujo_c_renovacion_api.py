"""Flujo C — renovación punta a punta por API (etapa 1 backend)."""
from __future__ import annotations

from datetime import date

import pytest

from app.comun.reloj import hoy_del_tenant
from app.storage.local import StorageLocal
from app.db import tenant_session
from tests import apoyo
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post
from tests.test_orquestacion import clave_de_matriz, insertar_matriz, insertar_oc, sesion  # noqa: F401
from tests.test_validacion_evidencia import _pdf, _subir, _validar


@pytest.fixture
def storage(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    return StorageLocal()


def _abrir_archivo(cliente_api, tenant, documento_id: str) -> None:
    r = cliente_api.post(
        f"/v1/storage/documentos/{documento_id}/url",
        headers=tenant.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text


def test_proponer_valida_vigencia_futura_y_posterior_al_vigente(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia validación C")
    persona = _alta_persona(cliente_api, t, "FLUJO-C-VAL", t.sujeto_tecnico)
    _cargar(cliente_api, t, persona, req, desde="2026-03-01", hasta="2026-12-31")
    with tenant_session(t.tenant_id) as s:
        hoy = hoy_del_tenant(s, t.tenant_id)
    r_pasado = _post(
        cliente_api,
        t,
        "tecnico",
        "proponer_documento",
        {
            "sujeto_id": persona,
            "requisito_definicion_id": req,
            "vigente_desde": "2026-03-01",
            "vigente_hasta": hoy.isoformat(),
        },
    )
    assert r_pasado.status_code == 422
    assert r_pasado.json()["error"]["codigo"] == "vigencia_no_futura"
    r_igual = _post(
        cliente_api,
        t,
        "tecnico",
        "proponer_documento",
        {
            "sujeto_id": persona,
            "requisito_definicion_id": req,
            "vigente_desde": "2026-03-01",
            "vigente_hasta": "2026-12-31",
        },
    )
    assert r_igual.status_code == 422
    assert r_igual.json()["error"]["codigo"] == "vigencia_no_posterior_a_vigente"


def test_flujo_c_confirmacion_exige_apertura_y_actualiza_acciones(cliente_api, storage, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia flujo C")
    persona = _alta_persona(cliente_api, t, "FLUJO-C-1", t.sujeto_tecnico)
    _cargar(cliente_api, t, persona, req, desde="2026-01-01", hasta="2026-10-12")
    clave = clave_de_matriz()
    insertar_matriz(sesion, t.tenant_id, clave, {req: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, "OC-FLUJO-C", clave, date(2026, 10, 1), date(2026, 10, 25))
    sesion.commit()

    acc_antes = cliente_api.get(
        "/v1/consultas/acciones_pendientes",
        params={"mes": "2026-10", "limit": 100},
        headers=t.headers("responsable_legajos"),
    ).json()["items"]
    assert any(i["legajo_id"] == persona for i in acc_antes)

    prop = _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2026-10-01",
                "vigente_hasta": "2027-06-30",
            },
        )
    )
    _subir(cliente_api, storage, t, prop["documento_id"], _pdf("licencia flujo c"), rol="tecnico")
    assert _validar(t, storage) == 1

    sin_abrir = cliente_api.post(
        "/v1/comandos/confirmar_documento",
        json={"documento_id": prop["documento_id"]},
        headers=t.headers("responsable_legajos"),
    )
    assert sin_abrir.status_code == 409
    assert sin_abrir.json()["error"]["codigo"] == "archivo_sin_apertura"
    assert "Abrí el archivo" in sin_abrir.json()["error"]["mensaje"]

    _abrir_archivo(cliente_api, t, prop["documento_id"])
    _ok(
        cliente_api.post(
            "/v1/comandos/confirmar_documento",
            json={"documento_id": prop["documento_id"]},
            headers=t.headers("responsable_legajos"),
        )
    )

    acc_despues = cliente_api.get(
        "/v1/consultas/acciones_pendientes",
        params={"mes": "2026-10", "limit": 100},
        headers=t.headers("responsable_legajos"),
    ).json()["items"]
    assert not any(i["legajo_id"] == persona and i.get("requisito") and "Licencia flujo C" in i["requisito"] for i in acc_despues)

    radar = cliente_api.get(
        "/v1/consultas/radar_documental_backlog",
        params={"desde": "2026-10-01", "hasta": "2026-10-31"},
        headers=t.headers("responsable_legajos"),
    )
    assert radar.status_code == 200


def test_flujo_c_rechazo_motivo_visible_en_mi_legajo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia rechazo C")
    persona = _alta_persona(cliente_api, t, "FLUJO-C-RECH", t.sujeto_tecnico)
    _cargar(cliente_api, t, persona, req, hasta="2026-12-31")
    prop = _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2027-01-01",
                "vigente_hasta": "2027-12-31",
            },
        )
    )
    motivo = "Foto borrosa — volver a enviar"
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "rechazar_propuesta",
            {"documento_id": prop["documento_id"], "motivo": motivo},
        )
    )
    legajo = cliente_api.get("/v1/consultas/mi_legajo", headers=t.headers("tecnico"))
    assert legajo.status_code == 200, legajo.text
    doc = next(d for d in legajo.json()["persona"]["documentos"] if d["requisito_definicion_id"] == req)
    assert doc["ultimo_rechazo_propuesta"]["motivo"] == motivo


def test_bandeja_revision_unifica_propuestas_y_archivos(cliente_api, storage, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Bandeja unificada C")
    persona = _alta_persona(cliente_api, t, "FLUJO-C-BAND", t.sujeto_tecnico)
    vig = _cargar(cliente_api, t, persona, req, hasta="2026-12-31", solo_declarado=True)
    prop = _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2027-01-01",
                "vigente_hasta": "2027-12-31",
            },
        )
    )
    _subir(cliente_api, storage, t, vig["documento_id"], _pdf("vigente bandeja"), rol="responsable_legajos")

    r = cliente_api.get(
        "/v1/consultas/bandeja_revision",
        params={"pestana": "todos", "limit": 50},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conteos"]["propuestas"] >= 1
    prop_item = next(i for i in body["items"] if i["documento_id"] == prop["documento_id"])
    assert prop_item["tipo_item"] == "propuesta"
    assert prop_item["vigente_comparacion"] is not None
    assert prop_item["propuesta"] is not None

    r_arch = cliente_api.get(
        "/v1/consultas/bandeja_revision",
        params={"pestana": "archivos", "limit": 50},
        headers=t.headers("responsable_legajos"),
    )
    assert r_arch.status_code == 200
    assert r_arch.json()["conteos"]["archivos"] >= 1
    assert any(i["documento_id"] == vig["documento_id"] and i["tipo_item"] == "archivo" for i in r_arch.json()["items"])
