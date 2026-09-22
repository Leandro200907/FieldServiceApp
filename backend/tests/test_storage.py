"""Storage de evidencia (A-02 / M-05 de la auditoría): claves derivadas en servidor, flujo
preparar → PUT firmado → confirmar (checksum y bytes medidos del archivo real), descarga
solo de archivos confirmados del propio tenant+documento, límites de tamaño y
Content-Type, y tests adversariales entre tenants y entre documentos.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests import apoyo
from sqlalchemy.exc import IntegrityError

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado, Prohibido
from app.auth.identidad import Identidad, Rol
from app.comun.reloj import ahora_utc
from app.db import tenant_session
from app.main import app
from app.storage.local import StorageLocal
from app.storage.servicio import confirmar_subida, firmar_descarga, preparar_subida
from app.worker import main as worker_main


def _pdf(texto: str) -> bytes:
    """PDF mínimo válido (mismo builder que tests/test_drive_nivel2_texto.py) con
    `texto` como contenido — para que la validación técnica (Fase 2 punto 2) lo acepte
    en los tests que esperan una descarga exitosa, distinguiendo igual el contenido por
    el `texto` que lleva adentro."""
    contenido = f"BT /F1 12 Tf 72 712 Td ({texto}) Tj ET".encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(contenido)).encode() + b" >>\nstream\n" + contenido + b"\nendstream",
    ]
    cuerpo = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objetos, start=1):
        offsets.append(len(cuerpo))
        cuerpo += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref_offset = len(cuerpo)
    n = len(objetos) + 1
    xref = f"xref\n0 {n}\n0000000000 65535 f \n".encode()
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()
    cuerpo += xref
    cuerpo += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return bytes(cuerpo)


def _validar_pendientes(t, storage) -> int:
    """Corre el job `validacion_evidencia` de verdad (Fase 2 punto 2) — `ahora=ahora_utc()`
    porque el productor (`confirmar_subida`) no es un proceso de reloj: encola con la hora
    real del request, así que hay que procesarlo con la hora real también."""
    return worker_main.procesar_cola(t.tenant_id, "validacion_evidencia", worker_main.HANDLERS["validacion_evidencia"],
                                     {"storage": storage}, ahora=ahora_utc())


@pytest.fixture
def storage(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    return StorageLocal()


@pytest.fixture
def api(storage):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _documento(tenant_id: str, sujeto_id: str = "persona_1", propuesta: bool = False) -> str:
    did = str(uuid.uuid4())
    with tenant_session(tenant_id) as s:
        apoyo.legajo(s, tenant_id, sujeto_id)
        s.execute(
            text(
                "INSERT INTO modulo1.documento (documento_id, tenant_id, sujeto_id, vigente_desde, vigente_hasta, origen, "
                "origen_propuesta, estado_confirmacion) VALUES (:d, :t, :sj, '2026-01-01', '2027-01-01', 'carga_manual', :p, "
                "CASE WHEN :p THEN 'declarado' ELSE 'verificado' END)"
            ),
            {"d": did, "t": tenant_id, "sj": sujeto_id, "p": propuesta},
        )
    return did


def _ident(t, rol: str) -> Identidad:
    return Identidad(t.tenant_id, t.usuarios[rol], frozenset({Rol(rol)}), t.sujeto_tecnico if rol == "tecnico" else None)


def _fila(tenant_id: str, documento_id: str) -> dict:
    with tenant_session(tenant_id) as s:
        return dict(s.execute(
            text("SELECT clave_storage, archivo_estado, checksum_archivo, archivo_bytes, archivo_content_type "
                 "FROM modulo1.documento WHERE documento_id = :d"), {"d": documento_id}).mappings().one())


def _subir_completo(api, storage, t, doc: str, contenido: bytes | None = None, rol="responsable_legajos", validar: bool = True) -> dict:
    contenido = _pdf("evidencia") if contenido is None else contenido
    prep = api.post("/v1/comandos/preparar_subida_de_evidencia", headers=t.headers(rol),
                    json={"documento_id": doc, "nombre_archivo": "apto.pdf", "content_type": "application/pdf"})
    assert prep.status_code == 200, prep.text
    put = api.put(prep.json()["url_subida"], content=contenido, headers={"Content-Type": "application/pdf"})
    assert put.status_code == 200, put.text
    conf = api.post("/v1/comandos/confirmar_subida_de_evidencia", headers=t.headers(rol), json={"documento_id": doc})
    assert conf.status_code == 200, conf.text
    if validar:
        _validar_pendientes(t, storage)
    return conf.json()


# --- flujo feliz -------------------------------------------------------------------
def test_flujo_preparar_put_confirmar_descargar(api, storage, tenant_de_prueba):
    t = tenant_de_prueba
    doc = _documento(t.tenant_id)
    contenido = _pdf("evidencia")
    conf = _subir_completo(api, storage, t, doc, contenido)
    fila = _fila(t.tenant_id, doc)
    assert fila["archivo_estado"] == "confirmado"
    assert fila["clave_storage"] == f"{t.tenant_id}/{doc}/apto.pdf"  # derivada en servidor
    assert fila["archivo_bytes"] == len(contenido) == conf["bytes"]
    assert fila["checksum_archivo"] == conf["checksum_sha256"] == storage.inspeccionar(fila["clave_storage"]).checksum_sha256
    url = api.get(f"/v1/storage/documentos/{doc}/url", headers=t.headers("responsable_legajos")).json()["url"]
    assert api.get(url).content == contenido
    # confirmar de nuevo es idempotente
    assert api.post("/v1/comandos/confirmar_subida_de_evidencia", headers=t.headers("responsable_legajos"),
                    json={"documento_id": doc}).json()["ya_confirmado"] is True
    # y no se re-prepara un confirmado (inmutabilidad de la versión)
    assert api.post("/v1/comandos/preparar_subida_de_evidencia", headers=t.headers("responsable_legajos"),
                    json={"documento_id": doc, "nombre_archivo": "otro.pdf", "content_type": "application/pdf"}).status_code == 409


def test_el_cliente_no_puede_elegir_la_clave_ni_el_checksum(api, tenant_de_prueba):
    """Los bodies públicos ya no aceptan clave_storage/checksum_archivo (se ignoran) y el
    nombre de archivo se sanea: la clave siempre es tenant/documento/nombre."""
    t = tenant_de_prueba
    req = api.post("/v1/comandos/dar_de_alta_definicion_de_requisito", headers=t.headers("configuracion"),
                   json={"nombre": "Apto", "categoria": "documento", "tipo_sujeto_aplicable": "persona"}).json()["requisito_definicion_id"]
    persona = api.post("/v1/comandos/alta_de_sujeto", headers=t.headers("responsable_legajos"),
                       json={"tipo_sujeto": "persona", "identificador_natural": "S-1"}).json()["sujeto_id"]
    r = api.post("/v1/comandos/cargar_documento", headers=t.headers("responsable_legajos"), json={
        "sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31",
        "clave_storage": "otro-tenant/otro-doc/x.pdf", "checksum_archivo": "deadbeef"})
    assert r.status_code == 200
    fila = _fila(t.tenant_id, r.json()["documento_id"])
    assert fila["clave_storage"] is None and fila["checksum_archivo"] is None and fila["archivo_estado"] == "sin_archivo"
    prep = api.post("/v1/comandos/preparar_subida_de_evidencia", headers=t.headers("responsable_legajos"),
                    json={"documento_id": r.json()["documento_id"], "nombre_archivo": "../../../etc/passwd", "content_type": "application/pdf"})
    assert prep.status_code == 200
    assert _fila(t.tenant_id, r.json()["documento_id"])["clave_storage"] == f"{t.tenant_id}/{r.json()['documento_id']}/passwd"


# --- adversarial: entre tenants ------------------------------------------------------
def test_adversarial_documento_de_A_no_puede_apuntar_a_clave_de_B(api, storage, dos_tenants):
    """Escenario A-02: el documento de A intenta referenciar el archivo físico de B."""
    ta, tb = dos_tenants
    doc_b = _documento(tb.tenant_id)
    _subir_completo(api, storage, tb, doc_b, _pdf("secreto de B"))
    clave_b = _fila(tb.tenant_id, doc_b)["clave_storage"]
    doc_a = _documento(ta.tenant_id)

    # 1) La base rechaza la fila inconsistente aunque alguien la escriba a mano.
    with pytest.raises(IntegrityError):
        with tenant_session(ta.tenant_id) as s:
            s.execute(text("UPDATE modulo1.documento SET clave_storage = :c, archivo_estado = 'confirmado', "
                           "checksum_archivo = 'x', archivo_bytes = 1 WHERE documento_id = :d"), {"c": clave_b, "d": doc_a})

    # 2) Aunque la base no existiera: el servicio re-deriva y rechaza (defensa en profundidad).
    #    Se simula desactivando temporalmente el CHECK vía monkeypatch del helper de lectura.
    from app.storage import servicio as srv
    original = srv._documento
    estado_simulado = {"valor": "confirmado"}

    def con_clave_ajena(session, documento_id, *, bloquear=False):
        d = original(session, documento_id, bloquear=bloquear)
        if str(d["documento_id"]) == doc_a:
            d.update({"clave_storage": clave_b, "archivo_estado": estado_simulado["valor"]})
        return d

    srv._documento = con_clave_ajena
    try:
        with tenant_session(ta.tenant_id) as s:
            with pytest.raises(Prohibido):
                firmar_descarga(s, _ident(ta, "responsable_legajos"), doc_a, storage=storage)
            estado_simulado["valor"] = "subida_pendiente"
            with pytest.raises(Prohibido):
                confirmar_subida(s, _ident(ta, "responsable_legajos"), doc_a, storage=storage)
            estado_simulado["valor"] = "confirmado"
        assert api.get(f"/v1/storage/documentos/{doc_a}/url", headers=ta.headers("responsable_legajos")).status_code == 403
    finally:
        srv._documento = original

    # 3) Sin JWT: una URL firmada solo puede nacer de firmar_descarga; la de B, usada sin
    #    token, sirve el archivo de B (es el diseño de URL prefirmada) pero con token de A
    #    se rechaza, y con una firma fabricada con otro secreto se rechaza siempre.
    url_b = api.get(f"/v1/storage/documentos/{doc_b}/url", headers=tb.headers("responsable_legajos")).json()["url"]
    assert api.get(url_b, headers=ta.headers("responsable_legajos")).status_code == 403
    fabricada = StorageLocal(secreto="otro-secreto").firmar(clave_b, "get", 60)
    assert api.get(f"/v1/storage/{fabricada}").status_code == 403
    # y no hay ningún camino por API para que A obtenga una firma sobre clave_b
    for rol in ("responsable_legajos", "supervisor", "tecnico", "configuracion"):
        assert api.get(f"/v1/storage/documentos/{doc_b}/url", headers=ta.headers(rol)).status_code in (403, 404)


def test_adversarial_entre_documentos_del_mismo_tenant(api, storage, tenant_de_prueba):
    """Un documento no puede apuntar al archivo de otro documento del mismo tenant."""
    t = tenant_de_prueba
    d1, d2 = _documento(t.tenant_id), _documento(t.tenant_id)
    _subir_completo(api, storage, t, d1, b"archivo de d1")
    clave_1 = _fila(t.tenant_id, d1)["clave_storage"]
    with pytest.raises(IntegrityError):
        with tenant_session(t.tenant_id) as s:
            s.execute(text("UPDATE modulo1.documento SET clave_storage = :c, archivo_estado = 'subida_pendiente' "
                           "WHERE documento_id = :d"), {"c": clave_1, "d": d2})
    assert _fila(t.tenant_id, d2)["archivo_estado"] == "sin_archivo"


# --- firma: vencimiento, tenant, secreto ----------------------------------------------
def test_firma_vencida_y_operacion_incorrecta(api, storage, tenant_de_prueba):
    t = tenant_de_prueba
    clave = storage.clave_para(t.tenant_id, str(uuid.uuid4()), "x.pdf")
    vencida = storage.firmar(clave, "get", 60, ahora=datetime.now(timezone.utc) - timedelta(seconds=120))
    assert api.get(f"/v1/storage/{vencida}").status_code == 403
    put_como_get = storage.firmar(clave, "put", 60, content_type="application/pdf", max_bytes=10)
    assert api.get(f"/v1/storage/{put_como_get}").status_code == 403


def test_bearer_invalido_en_url_firmada_da_401_aunque_el_bearer_sea_opcional(api, storage, tenant_de_prueba):
    """Auditoría externa (AUDITORIA_DB400E6, hallazgo A-03), con archivo real por HTTP (la
    auditoría lo marcó como hallazgo por inspección de código, sin esta prueba). El bearer
    de `/v1/storage/{firma}` es opcional — la firma es el permiso real — pero si SE MANDA
    uno, tiene que ser válido: `_exigir_tenant_del_token` lo decodifica igual."""
    t = tenant_de_prueba
    doc = _documento(t.tenant_id)
    prep = api.post("/v1/comandos/preparar_subida_de_evidencia", headers=t.headers("responsable_legajos"),
                    json={"documento_id": doc, "nombre_archivo": "apto.pdf", "content_type": "application/pdf"})
    assert prep.status_code == 200, prep.text
    url_subida = prep.json()["url_subida"]
    put = api.put(url_subida, content=_pdf("x"), headers={"Content-Type": "application/pdf", "Authorization": "Bearer token-invalido"})
    assert put.status_code == 401, put.text

    conf = _subir_completo(api, storage, t, doc)  # sube de nuevo, ok: preparar_subida no quedó bloqueado por el 401 de arriba
    url_descarga = api.get(f"/v1/storage/documentos/{doc}/url", headers=t.headers("responsable_legajos")).json()["url"]
    get = api.get(url_descarga, headers={"Authorization": "Bearer token-invalido"})
    assert get.status_code == 401, get.text


def test_secreto_de_storage_es_distinto_del_jwt(storage):
    from app.config import settings

    assert settings.storage_secret != settings.jwt_secret
    clave = storage.clave_para(str(uuid.uuid4()), "doc", "c.pdf")
    firmada_con_jwt = StorageLocal(secreto=settings.jwt_secret).firmar(clave, "get", 60)
    with pytest.raises(Prohibido):
        storage.verificar(firmada_con_jwt, "get")


# --- M-05: límites de subida ---------------------------------------------------------
def test_put_exige_content_type_y_respeta_tamano_maximo(api, storage, tenant_de_prueba, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "storage_max_bytes", 16)
    t = tenant_de_prueba
    doc = _documento(t.tenant_id)
    url = api.post("/v1/comandos/preparar_subida_de_evidencia", headers=t.headers("responsable_legajos"),
                   json={"documento_id": doc, "nombre_archivo": "a.pdf", "content_type": "application/pdf"}).json()["url_subida"]
    assert api.put(url, content=b"x" * 8).status_code == 403  # sin Content-Type
    assert api.put(url, content=b"x" * 8, headers={"Content-Type": "text/plain"}).status_code == 403
    assert api.put(url, content=b"x" * 17, headers={"Content-Type": "application/pdf"}).status_code == 422
    assert api.put(url, content=b"", headers={"Content-Type": "application/pdf"}).status_code == 422
    assert api.put(url, content=b"x" * 16, headers={"Content-Type": "application/pdf"}).status_code == 200
    # content_type no permitido se rechaza al preparar
    assert api.post("/v1/comandos/preparar_subida_de_evidencia", headers=t.headers("responsable_legajos"),
                    json={"documento_id": _documento(t.tenant_id), "nombre_archivo": "a.exe",
                          "content_type": "application/x-msdownload"}).status_code == 422


def test_confirmar_sin_archivo_subido_falla_y_no_confirma(api, storage, tenant_de_prueba):
    t = tenant_de_prueba
    doc = _documento(t.tenant_id)
    api.post("/v1/comandos/preparar_subida_de_evidencia", headers=t.headers("responsable_legajos"),
             json={"documento_id": doc, "nombre_archivo": "a.pdf", "content_type": "application/pdf"})
    r = api.post("/v1/comandos/confirmar_subida_de_evidencia", headers=t.headers("responsable_legajos"), json={"documento_id": doc})
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "archivo_ausente"
    assert _fila(t.tenant_id, doc)["archivo_estado"] == "subida_pendiente"
    # descargar un no confirmado no se firma
    assert api.get(f"/v1/storage/documentos/{doc}/url", headers=t.headers("responsable_legajos")).status_code == 422


# --- permisos --------------------------------------------------------------------------
def test_permisos_de_subida_y_descarga(api, storage, tenant_de_prueba):
    t = tenant_de_prueba
    propio = _documento(t.tenant_id, sujeto_id=t.sujeto_tecnico, propuesta=True)
    ajeno = _documento(t.tenant_id, sujeto_id="persona_otra")
    # técnico solo adjunta a su propia propuesta
    assert api.post("/v1/comandos/preparar_subida_de_evidencia", headers=t.headers("tecnico"),
                    json={"documento_id": ajeno, "nombre_archivo": "a.pdf", "content_type": "application/pdf"}).status_code == 403
    _subir_completo(api, storage, t, propio, _pdf("propio"), rol="tecnico")
    _subir_completo(api, storage, t, ajeno, _pdf("ajeno"))
    # supervisor no adjunta
    assert api.post("/v1/comandos/preparar_subida_de_evidencia", headers=t.headers("supervisor"),
                    json={"documento_id": ajeno, "nombre_archivo": "a.pdf", "content_type": "application/pdf"}).status_code == 403

    def pedir(rol, doc):
        return api.get(f"/v1/storage/documentos/{doc}/url", headers=t.headers(rol))

    assert pedir("responsable_legajos", ajeno).status_code == 200
    assert pedir("configuracion", ajeno).status_code == 403
    assert pedir("tecnico", ajeno).status_code == 403
    r = pedir("tecnico", propio)
    assert r.status_code == 200 and r.json()["eventos"] == ["DescargarArchivoDeEvidencia"]
    assert api.get(r.json()["url"]).content == _pdf("propio")
    assert pedir("supervisor", ajeno).status_code == 403
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                       "VALUES (:t, 'persona_otra', :u, '2026-01-01', 'test')"), {"t": t.tenant_id, "u": t.usuarios["supervisor"]})
    assert pedir("supervisor", ajeno).status_code == 200
    assert api.get(f"/v1/storage/documentos/{ajeno}/url").status_code == 401
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = 'DescargarArchivoDeEvidencia'")).scalar() == 3


def test_borrar_confirma_solo_si_desaparece(storage):
    clave = storage.clave_para(str(uuid.uuid4()), "x", "a.pdf")
    assert storage.borrar(clave) is True  # inexistente = ya no está
    storage.escribir(clave, b"1")
    assert storage.existe(clave) and storage.borrar(clave) is True and not storage.existe(clave)
