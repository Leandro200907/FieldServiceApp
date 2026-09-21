"""Validación técnica de evidencia (reauditoría Fase 2 punto 2, migración 0021): tests
adversariales sobre el eje `archivo_validacion`, el despacho caso A/caso B, el fencing por
token, el gate del motor puro, la distinción falla definitiva/transitoria, el dead-letter
notificado y la recuperación manual."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.comun.reloj import ahora_utc
from app.core.evaluacion import evaluar_documento_en_periodo
from app.core.orquestacion import decidir_habilitacion
from app.core.tipos import Documento, EstadoConfirmacion, EstadoVersionDocumento, Veredicto
from app.db import tenant_session
from app.modules.evidencia import servicio as evidencia
from app.modules.evidencia.servicio import verificar_archivo
from app.storage.local import StorageLocal
from app.worker import main as worker_main
from app.worker.cola import Job, encolar
from tests import apoyo
from tests.test_a07_revaluacion import _avisos, _outbox
from tests.test_comandos_legajos import _alta_def, _cargar, _ok, _post
from tests.test_orquestacion import clave_de_matriz, insertar_matriz, insertar_oc, sesion  # noqa: F401

AHORA = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def _pdf(texto: str) -> bytes:
    """Mismo builder mínimo que tests/test_storage.py y tests/test_drive_nivel2_texto.py."""
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


@pytest.fixture
def storage(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    return StorageLocal()


def _fila(tenant_id: str, documento_id: str) -> dict:
    with tenant_session(tenant_id) as s:
        return dict(s.execute(text(
            "SELECT estado_confirmacion, estado_version, archivo_estado, archivo_validacion, "
            "archivo_validacion_motivo, archivo_validacion_token, sucede_a "
            "FROM modulo1.documento WHERE documento_id = :d"), {"d": documento_id}).mappings().one())


def _subir(cliente_api, storage, t, doc: str, contenido: bytes, rol="responsable_legajos") -> None:
    prep = cliente_api.post("/v1/comandos/preparar_subida_de_evidencia", headers=t.headers(rol),
                            json={"documento_id": doc, "nombre_archivo": "e.pdf", "content_type": "application/pdf"})
    assert prep.status_code == 200, prep.text
    put = cliente_api.put(prep.json()["url_subida"], content=contenido, headers={"Content-Type": "application/pdf"})
    assert put.status_code == 200, put.text
    conf = cliente_api.post("/v1/comandos/confirmar_subida_de_evidencia", headers=t.headers(rol), json={"documento_id": doc})
    assert conf.status_code == 200, conf.text


def _validar(t, storage, ahora=None, max_jobs=10) -> int:
    return worker_main.procesar_cola(t.tenant_id, "validacion_evidencia", worker_main.HANDLERS["validacion_evidencia"],
                                     {"storage": storage}, ahora=ahora or ahora_utc(), max_jobs=max_jobs)


def _job(tenant_id: str, documento_id: str, token: str, intentos: int = 1) -> Job:
    return Job(id=1, tenant_id=tenant_id, cola="validacion_evidencia", payload={"documento_id": documento_id, "token": str(token)},
              intentos=intentos, lease_hasta=None, estado="en_curso", lease_token=None)


# --------------------------------------------------------------------------- verificación técnica pura


def test_verificar_archivo_nunca_afirma_escaneado_sin_scanner_real():
    valido, motivo, detalles = verificar_archivo(_pdf("ok"), "application/pdf")
    assert valido and motivo is None and detalles["scan_estado"] == "no_configurado"
    assert detalles["content_type_detectado"] == "application/pdf" and detalles["paginas"] == 1


def test_verificar_archivo_detecta_tipo_no_reconocible_y_mismatch():
    valido, motivo, _ = verificar_archivo(b"esto no es nada reconocible", "application/pdf")
    assert not valido and "no tiene un formato reconocible" in motivo
    valido, motivo, det = verificar_archivo(b"\xff\xd8\xff" + b"jpeg falso", "application/pdf")
    assert not valido and "no coincide con el tipo declarado" in motivo and det["content_type_detectado"] == "image/jpeg"


def test_verificar_archivo_pdf_corrupto_es_invalido():
    valido, motivo, _ = verificar_archivo(b"%PDF-1.4 pero esto no es un pdf de verdad", "application/pdf")
    assert not valido and "corrupto" in motivo


# --------------------------------------------------------------------------- caso A: declarado


def test_caso_a_declarado_invalido_rechaza_como_rechazar_propuesta(cliente_api, storage, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    persona = t.sujeto_tecnico
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, persona)
    original = _cargar(cliente_api, t, persona, req, hasta="2027-06-30")["documento_id"]

    r = _post(cliente_api, t, "tecnico", "proponer_documento",
              {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2028-01-01"})
    assert r.status_code == 200, r.text
    propuesta = r.json()["documento_id"]
    assert _fila(t.tenant_id, propuesta)["estado_confirmacion"] == "declarado"

    _subir(cliente_api, storage, t, propuesta, b"basura, no es un pdf", rol="tecnico")
    assert _validar(t, storage) == 1

    fila_propuesta = _fila(t.tenant_id, propuesta)
    assert fila_propuesta["archivo_validacion"] == "invalido"
    assert fila_propuesta["estado_version"] == "rechazada"  # Caso A: mismo camino que RechazarPropuesta

    assert _fila(t.tenant_id, original)["estado_version"] == "vigente"  # se restauró

    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tenant_id = :t AND tipo = 'DocumentoRechazado' "
                              "AND payload->>'documento_id' = :d"), {"t": t.tenant_id, "d": propuesta}).scalar() == 1
    prop = cliente_api.get("/v1/consultas/propuestas_pendientes", headers=t.headers("responsable_legajos")).json()
    assert propuesta not in {i["documento_id"] for i in prop["items"]}


# --------------------------------------------------------------------------- caso B: verificado


@pytest.fixture
def escenario_caso_b(sesion, cliente_api, tenant_de_prueba):
    """persona_A verificada (comando real, así se le puede adjuntar evidencia real), OC-1
    activa y una decisión D1 ya tomada — mismo espíritu que el escenario base de
    test_a07_revaluacion.py."""
    t = tenant_de_prueba
    req_p = _alta_def(cliente_api, t, "Apto médico")
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, "persona_A")
    doc = _cargar(cliente_api, t, "persona_A", req_p, hasta="2027-06-30")["documento_id"]
    clave = clave_de_matriz()
    with tenant_session(t.tenant_id) as s:
        insertar_matriz(s, t.tenant_id, clave, {req_p: "excepcionable"})
        insertar_oc(s, t.tenant_id, "OC-1", clave, date(2026, 10, 1), date(2026, 10, 5))
        d1 = decidir_habilitacion(s, t.tenant_id, "OC-1", ["persona_A"], AHORA, t.usuarios["responsable_legajos"])["referencia_evaluacion"]
    return {"t": t, "doc": doc, "req_p": req_p, "d1": d1}


def test_caso_b_verificado_invalido_no_toca_estado_confirmacion_notifica_y_revalua(cliente_api, storage, escenario_caso_b):
    e = escenario_caso_b
    t, doc = e["t"], e["doc"]
    assert _fila(t.tenant_id, doc)["estado_confirmacion"] == "verificado"

    _subir(cliente_api, storage, t, doc, b"no es un pdf de verdad")
    assert _validar(t, storage) == 1

    fila = _fila(t.tenant_id, doc)
    assert fila["archivo_validacion"] == "invalido"
    assert fila["estado_confirmacion"] == "verificado"  # NUNCA se toca solo (caso B)
    assert fila["estado_version"] == "vigente"  # tampoco se rechaza

    r = cliente_api.get(f"/v1/storage/documentos/{doc}/url", headers=t.headers("responsable_legajos"))
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "archivo_invalido"

    with tenant_session(t.tenant_id) as s:
        job = s.execute(text("SELECT payload FROM modulo1.job_queue WHERE tenant_id = :t AND cola = 'notificaciones' "
                             "AND payload->>'tipo' = 'EvidenciaInvalida'"), {"t": t.tenant_id}).mappings().first()
    assert job is not None and job["payload"]["documento_id"] == doc

    avisos = _avisos(t, e["d1"])
    assert [a["estado"] for a in avisos] == ["abierto"]
    ob = _outbox(t)
    assert len(ob) == 1 and ob[0]["payload"]["referencia_evaluacion"] == e["d1"]


def test_caso_b_evaluaciones_historicas_no_cambian_solo_las_nuevas_ven_requiere_revision(cliente_api, storage, escenario_caso_b):
    e = escenario_caso_b
    t, doc, req_p = e["t"], e["doc"], e["req_p"]

    with tenant_session(t.tenant_id) as s:
        veredicto_previo = s.execute(text("SELECT por_sujeto FROM modulo1.evaluacion_habilitacion WHERE referencia_evaluacion = :r"),
                                     {"r": e["d1"]}).scalar()

    _subir(cliente_api, storage, t, doc, b"no es un pdf de verdad")
    _validar(t, storage)

    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT por_sujeto FROM modulo1.evaluacion_habilitacion WHERE referencia_evaluacion = :r"),
                         {"r": e["d1"]}).scalar() == veredicto_previo  # inmutable

    with tenant_session(t.tenant_id) as s:
        nueva = decidir_habilitacion(s, t.tenant_id, "OC-1", ["persona_A"], AHORA, t.usuarios["responsable_legajos"])
    req = next(r for p in nueva["por_sujeto"] if p["sujeto_id"] == "persona_A" for r in p["requisitos"] if r["requisito_definicion_id"] == req_p)
    assert req["veredicto"] == "requiere_revision"


# --------------------------------------------------------------------------- motor puro


def _doc(**over) -> Documento:
    base = dict(documento_id="d1", sujeto_id="s1", requisito_definicion_id="r1",
               vigente_desde=date(2026, 1, 1), vigente_hasta=date(2027, 1, 1),
               estado_confirmacion=EstadoConfirmacion.VERIFICADO, estado_version=EstadoVersionDocumento.VIGENTE)
    base.update(over)
    return Documento(**base)


def test_motor_puro_archivo_requiere_revision():
    r = evaluar_documento_en_periodo(_doc(archivo_requiere_revision=True), date(2026, 6, 1))
    assert r.veredicto == Veredicto.REQUIERE_REVISION and "validación técnica" in r.motivo


def test_motor_puro_sin_archivo_adjunto_no_activa_el_gate():
    """Default False: acreditación/inducción y documentos sin archivo nunca lo activan —
    el cómputo real (confirmado+no-valido) se arma en orquestacion.py, no acá."""
    r = evaluar_documento_en_periodo(_doc(), date(2026, 6, 1))
    assert r.veredicto == Veredicto.HABILITADO


def test_motor_puro_declarado_gana_sobre_archivo_pendiente():
    r = evaluar_documento_en_periodo(_doc(estado_confirmacion=EstadoConfirmacion.DECLARADO, archivo_requiere_revision=True), date(2026, 6, 1))
    assert r.veredicto == Veredicto.REQUIERE_REVISION and "dato solo declarado" in r.motivo


# --------------------------------------------------------------------------- fencing


def test_fencing_job_viejo_no_pisa_archivo_reemplazado(cliente_api, storage, escenario_caso_b):
    e = escenario_caso_b
    t, doc = e["t"], e["doc"]
    _subir(cliente_api, storage, t, doc, b"malo, primera version")
    token_viejo = _fila(t.tenant_id, doc)["archivo_validacion_token"]

    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.documento SET archivo_validacion = 'invalido' WHERE documento_id = :d"), {"d": doc})
    _subir(cliente_api, storage, t, doc, _pdf("segunda version, buena"))
    token_nuevo = _fila(t.tenant_id, doc)["archivo_validacion_token"]
    assert str(token_viejo) != str(token_nuevo)

    with tenant_session(t.tenant_id) as s:
        evidencia.procesar(s, _job(t.tenant_id, doc, token_viejo), {"storage": storage})
        s.commit()
    assert str(_fila(t.tenant_id, doc)["archivo_validacion_token"]) == str(token_nuevo)  # sin cambios por el job viejo

    _validar(t, storage)
    assert _fila(t.tenant_id, doc)["archivo_validacion"] == "valido"


# --------------------------------------------------------------------------- falla definitiva vs transitoria


def test_documento_o_token_faltante_en_el_payload_es_terminal(tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        with pytest.raises(Exception) as info:
            evidencia.procesar(s, Job(id=1, tenant_id=t.tenant_id, cola="validacion_evidencia", payload={}, intentos=1,
                                      lease_hasta=None, estado="en_curso", lease_token=None), {})
    assert "JobNoProcesable" in type(info.value).__name__


def test_documento_inexistente_es_terminal(tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        with pytest.raises(Exception) as info:
            evidencia.procesar(s, _job(t.tenant_id, str(uuid.uuid4()), "x"), {})
    assert "JobNoProcesable" in type(info.value).__name__


def test_archivo_ausente_en_storage_es_terminal(cliente_api, storage, escenario_caso_b):
    e = escenario_caso_b
    t, doc = e["t"], e["doc"]
    _subir(cliente_api, storage, t, doc, _pdf("se va a borrar"))
    fila = _fila(t.tenant_id, doc)
    with tenant_session(t.tenant_id) as s:
        clave = s.execute(text("SELECT clave_storage FROM modulo1.documento WHERE documento_id = :d"), {"d": doc}).scalar()
    storage.borrar(clave)  # el archivo desaparece del storage entre confirmar y validar
    with tenant_session(t.tenant_id) as s:
        with pytest.raises(Exception) as info:
            evidencia.procesar(s, _job(t.tenant_id, doc, fila["archivo_validacion_token"]), {"storage": storage})
    assert "JobNoProcesable" in type(info.value).__name__


def test_storage_caido_es_transitorio_no_terminal(escenario_caso_b):
    """Cualquier excepción de `storage.leer` que no sea `FileNotFoundError` se deja
    propagar tal cual — nunca envuelta en JobNoProcesable — para que el worker reintente
    con su backoff genérico."""
    e = escenario_caso_b
    t = e["t"]

    class _StorageCaido:
        def leer(self, clave):
            raise ConnectionError("storage momentáneamente inaccesible")

    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.documento SET archivo_estado = 'confirmado', clave_storage = :c, "
                       "checksum_archivo = 'a', archivo_bytes = 1, archivo_validacion_token = gen_random_uuid() "
                       "WHERE documento_id = :d"), {"c": f"{t.tenant_id}/{e['doc']}/z.pdf", "d": e["doc"]})
        token = s.execute(text("SELECT archivo_validacion_token FROM modulo1.documento WHERE documento_id = :d"), {"d": e["doc"]}).scalar()
        with pytest.raises(ConnectionError):
            evidencia.procesar(s, _job(t.tenant_id, e["doc"], token), {"storage": _StorageCaido()})


# --------------------------------------------------------------------------- dead-letter notificado


def test_dead_letter_de_validacion_es_notificado(tenant_de_prueba):
    t = tenant_de_prueba

    class _StorageSiempreCaido:
        def leer(self, clave):
            raise ConnectionError("siempre caído")

    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, "persona_x")
        doc = s.execute(text(
            "INSERT INTO modulo1.documento (tenant_id, sujeto_id, vigente_desde, vigente_hasta, origen, estado_confirmacion) "
            "VALUES (:t, 'persona_x', '2026-01-01', '2027-01-01', 'carga_manual', 'verificado') RETURNING documento_id"),
            {"t": t.tenant_id}).scalar()
        s.execute(text(
            "UPDATE modulo1.documento SET archivo_estado = 'confirmado', clave_storage = :c, checksum_archivo = 'a', "
            "archivo_bytes = 1, archivo_validacion_token = gen_random_uuid() WHERE documento_id = :d"),
            {"c": f"{t.tenant_id}/{doc}/z.pdf", "d": doc})
        token = s.execute(text("SELECT archivo_validacion_token FROM modulo1.documento WHERE documento_id = :d"), {"d": doc}).scalar()
        jid = encolar(s, "validacion_evidencia", {"documento_id": str(doc), "token": str(token)}, tenant_id=t.tenant_id, disponible_en=AHORA)

    ahora = AHORA
    for _ in range(5):  # MAX_INTENTOS genérico del worker
        worker_main.procesar_cola(t.tenant_id, "validacion_evidencia", worker_main.HANDLERS["validacion_evidencia"],
                                  {"storage": _StorageSiempreCaido()}, ahora=ahora)
        ahora += timedelta(hours=2)

    with tenant_session(t.tenant_id) as s:
        estado = s.execute(text("SELECT estado FROM modulo1.job_queue WHERE id = :j"), {"j": jid}).scalar()
        alerta = s.execute(text("SELECT payload FROM modulo1.job_queue WHERE tenant_id = :t AND cola = 'notificaciones' "
                                "AND payload->>'tipo' = 'ValidacionEvidenciaEstancada'"), {"t": t.tenant_id}).mappings().first()
    assert estado == "fallido"
    assert alerta is not None and alerta["payload"]["documento_id"] == str(doc)


# --------------------------------------------------------------------------- recuperación manual


def test_reemplazo_de_archivo_invalido_permite_nueva_subida_y_valida(cliente_api, storage, escenario_caso_b):
    e = escenario_caso_b
    t, doc = e["t"], e["doc"]
    _subir(cliente_api, storage, t, doc, b"malo")
    _validar(t, storage)
    assert _fila(t.tenant_id, doc)["archivo_validacion"] == "invalido"

    _subir(cliente_api, storage, t, doc, _pdf("bueno ahora"))
    assert _fila(t.tenant_id, doc)["archivo_validacion"] == "pendiente"
    _validar(t, storage)
    assert _fila(t.tenant_id, doc)["archivo_validacion"] == "valido"
    assert cliente_api.get(f"/v1/storage/documentos/{doc}/url", headers=t.headers("responsable_legajos")).status_code == 200


def test_invalidar_evidencia_verificada_manual_responsable_only(cliente_api, storage, escenario_caso_b):
    e = escenario_caso_b
    t, doc = e["t"], e["doc"]
    _subir(cliente_api, storage, t, doc, _pdf("bueno"))
    _validar(t, storage)
    assert _fila(t.tenant_id, doc)["archivo_validacion"] == "valido"

    for rol in ("supervisor", "tecnico", "configuracion"):
        assert _post(cliente_api, t, rol, "invalidar_evidencia", {"documento_id": doc, "motivo": "x"}).status_code == 403

    r = _post(cliente_api, t, "responsable_legajos", "invalidar_evidencia",
              {"documento_id": doc, "motivo": "el número no coincide con el legajo"})
    assert r.status_code == 200, r.text
    fila = _fila(t.tenant_id, doc)
    assert fila["archivo_validacion"] == "invalido" and "el número no coincide" in fila["archivo_validacion_motivo"]
    assert fila["estado_confirmacion"] == "verificado"  # tampoco se toca acá

    with tenant_session(t.tenant_id) as s:
        job = s.execute(text("SELECT 1 FROM modulo1.job_queue WHERE tenant_id = :t AND cola = 'notificaciones' "
                             "AND payload->>'tipo' = 'EvidenciaInvalida'"), {"t": t.tenant_id}).first()
    assert job is not None
    assert _avisos(t, e["d1"])[0]["estado"] == "abierto"


def test_invalidar_evidencia_sobre_declarado_pide_usar_rechazar_propuesta(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    persona = t.sujeto_tecnico
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, persona)
    r = _post(cliente_api, t, "tecnico", "proponer_documento",
             {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2028-01-01"})
    doc = r.json()["documento_id"]
    r2 = _post(cliente_api, t, "responsable_legajos", "invalidar_evidencia", {"documento_id": doc, "motivo": "x"})
    assert r2.status_code == 422 and r2.json()["error"]["codigo"] == "usar_rechazar_propuesta"


def test_invalidar_evidencia_regenera_token_bloquea_job_viejo(cliente_api, storage, escenario_caso_b):
    """Un job automático que ya había leído el token viejo no puede validar por arriba de
    una invalidación manual posterior."""
    e = escenario_caso_b
    t, doc = e["t"], e["doc"]
    _subir(cliente_api, storage, t, doc, _pdf("bueno"))
    token_del_job = _fila(t.tenant_id, doc)["archivo_validacion_token"]

    _ok(_post(cliente_api, t, "responsable_legajos", "invalidar_evidencia", {"documento_id": doc, "motivo": "problema detectado a mano"}))
    assert _fila(t.tenant_id, doc)["archivo_validacion"] == "invalido"

    with tenant_session(t.tenant_id) as s:
        evidencia.procesar(s, _job(t.tenant_id, doc, token_del_job), {"storage": storage})
        s.commit()
    assert _fila(t.tenant_id, doc)["archivo_validacion"] == "invalido"  # el job viejo no lo pisó a "valido"


# --------------------------------------------------------------------------- bandeja / consulta


def test_bandeja_validacion_evidencia_por_defecto_solo_accion_requerida(cliente_api, storage, escenario_caso_b):
    e = escenario_caso_b
    t, doc = e["t"], e["doc"]
    _subir(cliente_api, storage, t, doc, b"malo")
    _validar(t, storage)

    r = cliente_api.get("/v1/consultas/bandeja_validacion_evidencia", headers=t.headers("responsable_legajos"))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["documento_id"] == doc and items[0]["archivo_validacion"] == "invalido"

    assert cliente_api.get("/v1/consultas/bandeja_validacion_evidencia", params={"estado": "valido"},
                           headers=t.headers("responsable_legajos")).json()["total"] == 0
    assert cliente_api.get("/v1/consultas/bandeja_validacion_evidencia", params={"estado": "todos"},
                           headers=t.headers("responsable_legajos")).json()["total"] == 1
    assert cliente_api.get("/v1/consultas/bandeja_validacion_evidencia", headers=t.headers("tecnico")).status_code == 403
    assert cliente_api.get("/v1/consultas/bandeja_validacion_evidencia", headers=t.headers("supervisor")).status_code == 403
