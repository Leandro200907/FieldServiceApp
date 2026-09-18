"""Storage local: URLs firmadas HMAC (PUT/GET), rechazo de firmas vencidas/ajenas/alteradas,
preparar_subida y firmar_descarga con auditoría en event_log, y el endpoint de descarga
autenticado. El router se monta a mano sobre la app (main.py es compartido)."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.errores import ErrorDeDominio, NoEncontrado, Prohibido, registrar_handlers
from app.comun.reloj import ahora_utc
from app.db import tenant_session
from app.storage.local import StorageLocal, sanear_nombre
from app.storage.servicio import firmar_descarga, preparar_subida


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    return StorageLocal()


@pytest.fixture
def api_storage(storage):
    from app.storage import router as router_mod

    app = FastAPI()
    registrar_handlers(app)
    app.include_router(router_mod.router, prefix="/v1")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _documento(tenant_id: str, sujeto_id: str = "persona_1", clave: str | None = None) -> str:
    did = str(uuid.uuid4())
    with tenant_session(tenant_id) as s:
        s.execute(
            text(
                "INSERT INTO modulo1.documento (documento_id, tenant_id, sujeto_id, vigente_desde, vigente_hasta, origen, clave_storage) "
                "VALUES (:d, :t, :sj, '2026-01-01', '2027-01-01', 'carga_manual', :c)"
            ),
            {"d": did, "t": tenant_id, "sj": sujeto_id, "c": clave},
        )
    return did


# --- firma ------------------------------------------------------------------------
def test_clave_estable_con_prefijo_de_tenant(storage):
    clave = storage.clave_para("T", "D", "../../etc/Mi Cert (2026).pdf")
    assert clave == "T/D/Mi_Cert_2026_.pdf"
    assert sanear_nombre("   ") == "archivo"


def test_put_y_get_firmados_funcionan(api_storage, storage):
    t, d = str(uuid.uuid4()), str(uuid.uuid4())
    clave = storage.clave_para(t, d, "cert.pdf")
    url_put = storage.url_prefirmada_put(clave, "application/pdf", 60)
    assert url_put.startswith("/v1/storage/")
    r = api_storage.put(url_put, content=b"%PDF-contenido", headers={"Content-Type": "application/pdf"})
    assert r.status_code == 200, r.text
    assert r.json()["clave_storage"] == clave and r.json()["bytes"] == 14
    assert storage.existe(clave)
    r = api_storage.get(storage.url_prefirmada_get(clave, 60))
    assert r.status_code == 200 and r.content == b"%PDF-contenido"
    # La firma de GET no sirve para PUT ni al revés.
    assert api_storage.put(storage.url_prefirmada_get(clave, 60), content=b"x").status_code == 403
    assert api_storage.get(url_put).status_code == 403
    # Content-Type distinto al firmado.
    assert api_storage.put(url_put, content=b"x", headers={"Content-Type": "image/png"}).status_code == 403


def test_firma_vencida_rechazada(api_storage, storage):
    t, d = str(uuid.uuid4()), str(uuid.uuid4())
    clave = storage.clave_para(t, d, "cert.pdf")
    firma = storage.firmar(clave, "get", 10, ahora=ahora_utc() - timedelta(seconds=30))
    r = api_storage.get(f"/v1/storage/{firma}")
    assert r.status_code == 403 and "venci" in r.json()["error"]["mensaje"]
    with pytest.raises(Prohibido):
        storage.verificar(firma, "get")


def test_firma_de_otro_tenant_o_alterada_rechazada(api_storage, storage, tenant_de_prueba):
    t_a, t_b, d = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    clave_a = storage.clave_para(t_a, d, "cert.pdf")
    # Firma emitida con otro secreto (otro emisor): HMAC no cierra.
    ajena = StorageLocal(secreto="otro-secreto").firmar(clave_a, "get", 60)
    assert api_storage.get(f"/v1/storage/{ajena}").status_code == 403
    # Firma válida cuyo cuerpo dice tenant B pero la clave es de A: rechazada.
    firma_b = storage.firmar(storage.clave_para(t_b, d, "cert.pdf"), "get", 60)
    datos_b, mac_b = firma_b.split(".")
    firma_a = storage.firmar(clave_a, "get", 60)
    datos_a, _ = firma_a.split(".")
    assert api_storage.get(f"/v1/storage/{datos_a}.{mac_b}").status_code == 403  # mac de otro cuerpo
    # Token JWT de un tenant distinto al de la firma: rechazado aunque la firma sea válida.
    clave_t = storage.clave_para(tenant_de_prueba.tenant_id, d, "cert.pdf")
    storage.escribir(clave_t, b"x")
    ok = storage.url_prefirmada_get(clave_t, 60)
    assert api_storage.get(ok, headers=tenant_de_prueba.headers("responsable_legajos")).status_code == 200
    from tests.conftest import token_para

    otro = {"Authorization": f"Bearer {token_para(t_b, str(uuid.uuid4()), ['responsable_legajos'])}"}
    assert api_storage.get(ok, headers=otro).status_code == 403
    # Firma con basura.
    assert api_storage.get("/v1/storage/no-es-una-firma").status_code == 403


def test_borrar_confirma_solo_si_desaparece(storage):
    clave = storage.clave_para(str(uuid.uuid4()), str(uuid.uuid4()), "a.pdf")
    assert storage.borrar(clave) is True  # inexistente: ya no está, se confirma
    storage.escribir(clave, b"x")
    assert storage.existe(clave)
    assert storage.borrar(clave) is True and not storage.existe(clave)
    with pytest.raises(Prohibido):
        storage.ruta("../fuera")


# --- servicio ---------------------------------------------------------------------
def test_preparar_subida_guarda_clave_y_devuelve_url_put(storage, tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    d = _documento(t)
    with tenant_session(t) as s:
        url = preparar_subida(s, t, tenant_de_prueba.usuarios["responsable_legajos"], d, "cert.pdf", "application/pdf", storage=storage)
    assert url.startswith("/v1/storage/")
    cuerpo = storage.verificar(url.rsplit("/", 1)[1], "put")
    assert cuerpo["clave"] == f"{t}/{d}/cert.pdf" and cuerpo["ct"] == "application/pdf"
    with tenant_session(t) as s:
        assert s.execute(text("SELECT clave_storage FROM modulo1.documento WHERE documento_id = :d"), {"d": d}).scalar() == cuerpo["clave"]
        with pytest.raises(NoEncontrado):
            preparar_subida(s, t, "u", str(uuid.uuid4()), "x.pdf", "application/pdf", storage=storage)


def test_firmar_descarga_audita_en_event_log(storage, tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    usuario = tenant_de_prueba.usuarios["responsable_legajos"]
    d = _documento(t, clave=f"{t}/x/cert.pdf")
    sin_archivo = _documento(t)
    with tenant_session(t) as s:
        url = firmar_descarga(s, t, usuario, d, expira_seg=120, storage=storage)
        with pytest.raises(ErrorDeDominio):
            firmar_descarga(s, t, usuario, sin_archivo, storage=storage)
        with pytest.raises(NoEncontrado):
            firmar_descarga(s, t, usuario, str(uuid.uuid4()), storage=storage)
    assert storage.verificar(url.rsplit("/", 1)[1], "get")["clave"] == f"{t}/x/cert.pdf"
    with tenant_session(t) as s:
        filas = s.execute(text("SELECT payload FROM modulo1.event_log WHERE tipo = 'DescargarArchivoDeEvidencia'")).all()
        assert len(filas) == 1
        p = filas[0][0]
        assert p["documento_id"] == d and p["clave_storage"] == f"{t}/x/cert.pdf" and p["usuario_id"] == usuario and "expira_en" in p
        # La URL/firma nunca se persiste.
        assert "url" not in p and "firma" not in p
    # Otro tenant no ve el documento (RLS) → NoEncontrado.
    with tenant_session(str(uuid.uuid4())) as s:
        with pytest.raises(NoEncontrado):
            firmar_descarga(s, t, usuario, d, storage=storage)


def test_endpoint_descarga_respeta_matriz_de_permisos(api_storage, storage, tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    propio = _documento(t, sujeto_id=tenant_de_prueba.sujeto_tecnico, clave=f"{t}/a/propio.pdf")
    ajeno = _documento(t, sujeto_id="persona_otra", clave=f"{t}/b/ajeno.pdf")
    storage.escribir(f"{t}/a/propio.pdf", b"propio")

    def pedir(rol, doc):
        return api_storage.get(f"/v1/storage/documentos/{doc}/url", headers=tenant_de_prueba.headers(rol))

    assert pedir("responsable_legajos", ajeno).status_code == 200
    assert pedir("configuracion", ajeno).status_code == 403
    assert pedir("tecnico", ajeno).status_code == 403
    r = pedir("tecnico", propio)
    assert r.status_code == 200 and r.json()["eventos"] == ["DescargarArchivoDeEvidencia"]
    # La URL devuelta funciona y sirve el archivo.
    assert api_storage.get(r.json()["url"]).content == b"propio"
    # Supervisor: fuera de su universo → 403; con asignación vigente → 200.
    assert pedir("supervisor", ajeno).status_code == 403
    with tenant_session(t) as s:
        s.execute(
            text(
                "INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                "VALUES (:t, 'persona_otra', :u, '2026-01-01', 'test')"
            ),
            {"t": t, "u": tenant_de_prueba.usuarios["supervisor"]},
        )
    assert pedir("supervisor", ajeno).status_code == 200
    assert api_storage.get(f"/v1/storage/documentos/{ajeno}/url").status_code == 401
