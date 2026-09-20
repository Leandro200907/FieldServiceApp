"""H-01: capacidades del anexo "Alcance de la v1": notificaciones reales (mail/Telegram,
entrega idempotente), paquete público con QR, score de salud documental, exportación
de legajo y Drive de solo lectura con bandeja de excepciones."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db import tenant_session
from app.modules.drive.proveedor import ArchivoRemoto, ProveedorEnMemoria
from app.modules.notificaciones import servicio as notif
from app.modules.notificaciones.canales import CanalFalso
from app.worker import main as worker_main
from app.worker.cola import encolar, tomar
from app.worker.outbox import PublicadorEnMemoria
from tests import apoyo
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post

T0 = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)


class _Storage:
    def __init__(self, tmp):
        from app.storage.local import StorageLocal
        self.real = StorageLocal(directorio=tmp, secreto="s" * 32)

    def __getattr__(self, n):
        return getattr(self.real, n)


# =========================================================================== notificaciones


def _job(t, payload):
    with tenant_session(t.tenant_id) as s:
        return encolar(s, "notificaciones", payload, tenant_id=t.tenant_id)


def _envios(t, job_id):
    with tenant_session(t.tenant_id) as s:
        return [dict(f) for f in s.execute(text("SELECT canal, destinatario, estado, intentos, error FROM modulo1.notificacion_envio WHERE tenant_id = :t AND job_id = :j ORDER BY canal, destinatario"),
                                           {"t": t.tenant_id, "j": job_id}).mappings()]


def test_configurar_canales_y_vincular_telegram(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    assert _post(cliente_api, t, "responsable_legajos", "configurar_canales", {"mail_habilitado": True}).status_code == 403
    r = _post(cliente_api, t, "configuracion", "configurar_canales", {"mail_habilitado": True, "telegram_habilitado": True, "remitente_nombre": "ACME HSE"})
    assert r.status_code == 200 and r.json()["mail_habilitado"] and r.json()["whatsapp"] == "disenado_no_activo"
    assert _post(cliente_api, t, "configuracion", "vincular_telegram", {"usuario_id": t.usuarios["supervisor"], "chat_id": "abc"}).status_code == 422
    assert _post(cliente_api, t, "configuracion", "vincular_telegram", {"usuario_id": t.usuarios["supervisor"], "chat_id": "123456789"}).status_code == 200
    assert _post(cliente_api, t, "configuracion", "vincular_telegram", {"usuario_id": str(uuid.uuid4()), "chat_id": "1"}).status_code == 404
    cfg = cliente_api.get("/v1/consultas/configuracion_canales", headers=t.headers("responsable_legajos")).json()
    assert cfg["usuarios_con_telegram"] == 1 and cfg["telegram_habilitado"] is True
    assert _post(cliente_api, t, "configuracion", "vincular_telegram", {"usuario_id": t.usuarios["supervisor"], "chat_id": None}).status_code == 200
    assert cliente_api.get("/v1/consultas/configuracion_canales", headers=t.headers("configuracion")).json()["usuarios_con_telegram"] == 0


def test_entrega_por_mail_y_telegram_idempotente_y_con_reintento(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _ok(_post(cliente_api, t, "configuracion", "configurar_canales", {"mail_habilitado": True, "telegram_habilitado": True}))
    _ok(_post(cliente_api, t, "configuracion", "vincular_telegram", {"usuario_id": t.usuarios["supervisor"], "chat_id": "555"}))
    payload = {"tipo": "AlertasDeVencimiento", "destinatario_rol": "supervisor", "destinatario_usuario_id": t.usuarios["supervisor"], "prioridad": "alta",
               "alertas": [{"sujeto_id": "p1", "tipo_sujeto": "persona", "requisito": "Apto", "vigente_hasta": "2026-12-31", "etapa": "vencido", "bajo_excepcion": False}]}
    jid = _job(t, payload)
    mail, tg = CanalFalso("mail"), CanalFalso("telegram", fallar_veces=1)
    canales = {"mail": mail, "telegram": tg}
    # primera pasada: mail ok, telegram falla → el job reintenta (fallido) y la traza lo dice
    n = worker_main.procesar_cola(t.tenant_id, "notificaciones", worker_main.handler_notificaciones, {"canales": canales}, ahora=T0)
    assert n == 1 and len(mail.enviados) == 1 and mail.enviados[0]["destino"].startswith("supervisor@") and "URGENTE" in mail.enviados[0]["asunto"]
    with tenant_session(t.tenant_id) as s:
        estado = s.execute(text("SELECT estado FROM modulo1.job_queue WHERE id = :j"), {"j": jid}).scalar()
    assert estado == "pendiente"
    assert [(e["canal"], e["estado"]) for e in _envios(t, jid)] == [("mail", "enviado"), ("telegram", "fallido")]
    # segunda pasada (tras el backoff): sólo se reenvía telegram; el mail NO se duplica (M-07)
    worker_main.procesar_cola(t.tenant_id, "notificaciones", worker_main.handler_notificaciones, {"canales": canales}, ahora=T0 + timedelta(hours=1))
    assert len(mail.enviados) == 1 and len(tg.enviados) == 1 and tg.enviados[0]["destino"] == "555"
    assert [(e["canal"], e["estado"], e["intentos"]) for e in _envios(t, jid)] == [("mail", "enviado", 1), ("telegram", "enviado", 2)]
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT estado FROM modulo1.job_queue WHERE id = :j"), {"j": jid}).scalar() == "completado"
    # rol broadcast: todos los responsables activos por mail
    jid2 = _job(t, {"tipo": "OcSinMatriz", "destinatario_rol": "responsable_legajos", "clave_origen": "OC-1"})
    worker_main.procesar_cola(t.tenant_id, "notificaciones", worker_main.handler_notificaciones, {"canales": canales}, ahora=T0)
    assert mail.enviados[-1]["destino"].startswith("responsable_legajos@") and "OC-1" in mail.enviados[-1]["asunto"]


def test_sin_canal_habilitado_queda_constancia_en_log_sin_llamar_proveedores(cliente_api, tenant_de_prueba, caplog):
    import logging
    t = tenant_de_prueba
    mail = CanalFalso("mail")
    jid = _job(t, {"tipo": "PlantillaGlobalActualizada", "destinatario_rol": "responsable_legajos", "nombre": "Apto", "version_nueva": 2, "copiada_de_version": 1, "plantilla_tipo": "definicion_requisito"})
    with caplog.at_level(logging.WARNING, logger="modulo1.notificaciones"):
        worker_main.procesar_cola(t.tenant_id, "notificaciones", worker_main.handler_notificaciones, {"canales": {"mail": mail}}, ahora=T0)
    assert mail.enviados == [] and "sin canal externo" in caplog.text
    assert [(e["canal"], e["estado"]) for e in _envios(t, jid)] == [("log", "enviado")]


def test_canal_real_no_configurado_falla_visible(cliente_api, tenant_de_prueba, monkeypatch):
    """Sin SMTP_HOST / TELEGRAM_BOT_TOKEN el envío queda `fallido` con error saneado, nunca un 500 silencioso."""
    from app.modules.notificaciones.canales import CanalMail, CanalTelegram
    for v in ("SMTP_HOST", "SMTP_FROM", "TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    t = tenant_de_prueba
    _ok(_post(cliente_api, t, "configuracion", "configurar_canales", {"mail_habilitado": True}))
    jid = _job(t, {"tipo": "OcSinMatriz", "destinatario_rol": "configuracion", "clave_origen": "X"})
    worker_main.procesar_cola(t.tenant_id, "notificaciones", worker_main.handler_notificaciones, {"canales": {"mail": CanalMail(), "telegram": CanalTelegram()}}, ahora=T0)
    e = _envios(t, jid)
    assert e[0]["estado"] == "fallido" and "SMTP_HOST" in e[0]["error"]


def test_render_de_mensajes():
    asunto, texto = notif.render({"tipo": "AlertasDeVencimiento", "prioridad": "normal", "alertas": [
        {"sujeto_id": "p", "tipo_sujeto": "persona", "requisito": "Apto", "vigente_hasta": "2026-12-31", "etapa": "aviso", "bajo_excepcion": True}]})
    assert asunto == "1 vencimiento(s) documental(es)" and "[bajo excepción]" in texto
    assert "matriz" in notif.render({"tipo": "OcSinMatriz", "clave_origen": "OC-9"})[1]


# =========================================================================== paquete público con QR


@pytest.fixture
def persona_con_docs(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    req2 = _alta_def(cliente_api, t, "Altura", categoria="competencia")
    p = _alta_persona(cliente_api, t, "DNI 30.000.000")
    _cargar(cliente_api, t, p, req, desde="2026-01-01", hasta="2027-12-31")
    _cargar(cliente_api, t, p, req2, desde="2026-01-01", hasta="2027-12-31", estado_confirmacion="declarado")
    return {"t": t, "persona": p, "req": req}


def test_paquete_publico_firmado_con_qr_vencimiento_y_revocacion(cliente_api, persona_con_docs):
    t, p = persona_con_docs["t"], persona_con_docs["persona"]
    assert _post(cliente_api, t, "supervisor", "generar_paquete_entrega", {"sujeto_id": p}).status_code == 403
    assert _post(cliente_api, t, "responsable_legajos", "generar_paquete_entrega", {"sujeto_id": "nadie"}).status_code == 404
    r = _post(cliente_api, t, "responsable_legajos", "generar_paquete_entrega", {"sujeto_id": p, "dias_validez": 7})
    assert r.status_code == 200, r.text
    url, url_qr, paquete_id = r.json()["url"], r.json()["url_qr"], r.json()["paquete_id"]
    token = url.rsplit("/", 1)[1]
    assert len(token) > 50 and "." in token
    # público: sin JWT; sólo estados, sin archivos ni ids internos
    pub = cliente_api.get(f"/v1/publico/paquete/{token}")
    assert pub.status_code == 200, pub.text
    c = pub.json()
    assert c["sujeto"] == {"sujeto_id": p, "tipo_sujeto": "persona", "identificador": "DNI 30.000.000"}
    assert {x["requisito"]: x["estado"] for x in c["requisitos"]} == {"Apto médico": "vigente", "Altura": "declarado_sin_verificar"}
    assert "documento_id" not in pub.text and "clave_storage" not in pub.text and "url" not in pub.text
    qr = cliente_api.get(f"/v1/publico/paquete/{token}/qr.png")
    assert qr.status_code == 200 and qr.headers["content-type"] == "image/png" and qr.content[:8] == b"\x89PNG\r\n\x1a\n"
    # traza de accesos
    lista = cliente_api.get("/v1/consultas/paquetes_entrega", params={"sujeto_id": p}, headers=t.headers("responsable_legajos")).json()["items"]
    assert lista[0]["accesos"] == 1 and lista[0]["vigente"] is True
    # token manipulado / inexistente → 404 (no enumerable, sin tocar la base para firmas inválidas)
    assert cliente_api.get(f"/v1/publico/paquete/{token[:-3]}xyz").status_code == 404
    assert cliente_api.get("/v1/publico/paquete/no-existe").status_code == 404
    # revocado → 404
    assert _post(cliente_api, t, "responsable_legajos", "revocar_paquete_entrega", {"paquete_id": paquete_id}).status_code == 200
    assert cliente_api.get(f"/v1/publico/paquete/{token}").status_code == 404
    assert cliente_api.get(f"/v1/publico/paquete/{token}/qr.png").status_code == 404
    assert _post(cliente_api, t, "responsable_legajos", "revocar_paquete_entrega", {"paquete_id": paquete_id}).status_code == 409
    # vencido → 404
    r2 = _ok(_post(cliente_api, t, "responsable_legajos", "generar_paquete_entrega", {"sujeto_id": p, "dias_validez": 1}))
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.paquete_entrega SET expira_en = now() - interval '1 minute' WHERE paquete_id = :p"), {"p": r2["paquete_id"]})
    assert cliente_api.get(f"/v1/publico/paquete/{r2['url'].rsplit('/', 1)[1]}").status_code == 404


def test_paquete_rate_limit_y_aislamiento(cliente_api, persona_con_docs, monkeypatch):
    from app.modules.paquete import servicio as paq
    t, p = persona_con_docs["t"], persona_con_docs["persona"]
    r = _ok(_post(cliente_api, t, "responsable_legajos", "generar_paquete_entrega", {"sujeto_id": p}))
    token = r["url"].rsplit("/", 1)[1]
    monkeypatch.setattr(paq, "limiter", paq.RateLimiter(max_por_minuto=3))
    codigos = [cliente_api.get(f"/v1/publico/paquete/{token}").status_code for _ in range(5)]
    assert codigos == [200, 200, 200, 422, 422]
    assert cliente_api.get(f"/v1/publico/paquete/{token}").json()["error"]["codigo"] == "rate_limit"
    # el token pertenece a su tenant: el hash sólo resuelve a ese tenant (función SECURITY DEFINER)
    monkeypatch.setattr(paq, "limiter", paq.RateLimiter(max_por_minuto=100))
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.paquete_acceso WHERE tenant_id = :t"), {"t": t.tenant_id}).scalar() == 3


# =========================================================================== score


def test_score_documental_y_snapshot_diario(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    req2 = _alta_def(cliente_api, t, "Altura", categoria="competencia")
    p1, p2 = _alta_persona(cliente_api, t, "1"), _alta_persona(cliente_api, t, "2")
    with tenant_session(t.tenant_id) as s:
        apoyo.supervisor_de(s, t, p1)
    mat = _post(cliente_api, t, "configuracion", "publicar_version_de_matriz", {
        "cliente_id": str(uuid.uuid4()), "locacion_id": str(uuid.uuid4()), "tipo_servicio_id": str(uuid.uuid4()), "vigente_desde": "2026-01-01",
        "lineas": [{"requisito_definicion_id": req, "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True},
                   {"requisito_definicion_id": req2, "clasificacion": "excepcionable", "bloqueante_durante_ejecucion": False}]})
    assert mat.status_code == 200
    _cargar(cliente_api, t, p1, req, desde="2026-01-01", hasta="2027-12-31")                       # verificado: cubre
    _post(cliente_api, t, "tecnico", "proponer_documento", {"sujeto_id": p2, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2027-12-31"})
    r = cliente_api.get("/v1/consultas/score_documental", headers=t.headers("responsable_legajos")).json()
    # 2 personas × 2 requisitos exigidos = 4; cubierto sólo p1/req (el declarado de p2 no cuenta)
    assert (r["exigidos"], r["cubiertos"], r["score"]) == (4, 1, 25.0)
    assert r["por_tipo_sujeto"]["persona"]["sujetos"] == 2 and r["peores"][0]["sujeto_id"] == p2 and r["sujetos_completos"] == 0
    sup = cliente_api.get("/v1/consultas/score_documental", headers=t.headers("supervisor")).json()
    assert (sup["exigidos"], sup["cubiertos"], sup["score"]) == (2, 1, 50.0)                        # sólo su universo (p1)
    assert cliente_api.get("/v1/consultas/score_documental", headers=t.headers("tecnico")).status_code == 403
    # snapshot diario por el worker: el reloj encola una vez por día; el handler es idempotente por fecha
    from app.modules.score.servicio import encolar_snapshot_diario
    with tenant_session(t.tenant_id) as s:
        assert encolar_snapshot_diario(s, t.tenant_id, T0) == {"score_jobs": 1}
        assert encolar_snapshot_diario(s, t.tenant_id, T0 + timedelta(hours=2)) == {"score_jobs": 0}
    for _ in range(2):
        worker_main.procesar_cola(t.tenant_id, "score_documental", worker_main.handler_score_documental, {}, ahora=T0)
    with tenant_session(t.tenant_id) as s:
        filas = s.execute(text("SELECT fecha, score FROM modulo1.score_snapshot WHERE tenant_id = :t"), {"t": t.tenant_id}).all()
    assert len(filas) == 1 and float(filas[0][1]) == 25.0
    assert cliente_api.get("/v1/consultas/score_documental", headers=t.headers("configuracion")).json()["historial"][0]["score"] == 25.0


# =========================================================================== exportación


def test_exportar_legajo_json_y_csv_con_traza(cliente_api, persona_con_docs):
    t, p = persona_con_docs["t"], persona_con_docs["persona"]
    assert cliente_api.get("/v1/consultas/exportar_legajo", params={"sujeto_id": p}, headers=t.headers("supervisor")).status_code == 403
    assert cliente_api.get("/v1/consultas/exportar_legajo", params={"sujeto_id": "nadie"}, headers=t.headers("responsable_legajos")).status_code == 404
    r = cliente_api.get("/v1/consultas/exportar_legajo", params={"sujeto_id": p}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json") and "attachment" in r.headers["content-disposition"]
    d = r.json()
    assert d["legajo"]["sujeto_id"] == p and len(d["documentos"]) == 2 and d["documentos"][0]["requisito"] in ("Apto médico", "Altura")
    assert {"acreditaciones", "inducciones", "excepciones", "constancias", "custodias", "alertas", "supervision"} <= set(d)
    csv = cliente_api.get("/v1/consultas/exportar_legajo", params={"sujeto_id": p, "formato": "csv"}, headers=t.headers("responsable_legajos"))
    assert csv.status_code == 200 and csv.text.startswith("seccion,campo,valor,fila\n") and "documentos,requisito," in csv.text
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tenant_id = :t AND tipo = 'LegajoExportado'"), {"t": t.tenant_id}).scalar() == 2


# =========================================================================== Drive


def _remoto(id_, nombre, mime="application/pdf", h=None):
    return ArchivoRemoto(id_, nombre, mime, datetime(2026, 9, 1, tzinfo=timezone.utc), h or f"h-{id_}", 100)


@pytest.fixture
def drive(cliente_api, tenant_de_prueba, tmp_path):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    _alta_def(cliente_api, t, "Altura en andamios", categoria="competencia")
    _alta_def(cliente_api, t, "Altura avanzada", categoria="competencia")
    p = _alta_persona(cliente_api, t, "DNI 1", sujeto_id="persona_0042")
    prov = ProveedorEnMemoria(carpetas={"carpeta-1": [
        _remoto("a1", "persona_0042__Apto_medico__2027-06-30.pdf"),                 # alta
        _remoto("a2", "persona_0042__Apto_medico__2027-06-30__2026-07-01.pdf"),     # alta con desde (misma clave → renovación sin cambios? distinto hash)
        _remoto("m1", "persona_0042__Altura__2027-06-30.pdf"),                      # media: requisito ambiguo (en andamios / avanzada)
        _remoto("b1", "persona_9999__Apto_medico__2027-06-30.pdf"),                 # baja: sujeto inexistente
        _remoto("b2", "foto.jpg", mime="image/jpeg"),                               # baja: sin convención
        _remoto("b3", "persona_0042__Apto_medico__2027-06-30.docx", mime="application/msword"),  # baja: tipo no aceptado
    ]}, contenidos={k: b"%PDF-1.4 contenido " + k.encode() for k in ("a1", "a2", "m1", "b1", "b2", "b3")})
    return {"t": t, "persona": p, "req": req, "prov": prov, "storage": _Storage(tmp_path)}


def test_drive_configuracion_y_escaneo_con_bandeja(cliente_api, drive, monkeypatch):
    from app.modules import capacidades_router as cr
    t, prov, storage = drive["t"], drive["prov"], drive["storage"]
    monkeypatch.setattr(cr, "_proveedor_drive", lambda: prov)
    monkeypatch.setattr(cr, "_storage", lambda: storage)
    assert _post(cliente_api, t, "responsable_legajos", "escanear_drive", {}).status_code == 422          # drive_no_habilitado
    assert _post(cliente_api, t, "configuracion", "configurar_drive", {"habilitado": True}).status_code == 422   # carpeta_requerida
    assert _post(cliente_api, t, "supervisor", "configurar_drive", {"habilitado": True, "carpeta_id": "x"}).status_code == 403
    assert _post(cliente_api, t, "configuracion", "configurar_drive", {"habilitado": True, "carpeta_id": "carpeta-1", "intervalo_horas": 6}).status_code == 200
    r = _post(cliente_api, t, "responsable_legajos", "escanear_drive", {})
    assert r.status_code == 200, r.text
    assert {k: r.json()[k] for k in ("vistos", "nuevos", "importados", "bandeja")} == {"vistos": 6, "nuevos": 6, "importados": 2, "bandeja": 4}
    # importados: documento declarado, origen drive, archivo confirmado con checksum real
    with tenant_session(t.tenant_id) as s:
        docs = s.execute(text("SELECT origen, estado_confirmacion, origen_propuesta, archivo_estado, archivo_bytes, estado_version FROM modulo1.documento "
                              "WHERE tenant_id = :t AND sujeto_id = 'persona_0042' ORDER BY version"), {"t": t.tenant_id}).all()
    assert [d[0] for d in docs] == ["drive", "drive"] and all(d[1] == "declarado" and d[2] is True and d[3] == "confirmado" and d[4] > 0 for d in docs)
    assert [d[5] for d in docs] == ["sucedida", "vigente"]
    assert sorted(prov.descargas) == ["a1", "a2"]
    # bandeja: media y bajas con motivo
    band = cliente_api.get("/v1/consultas/bandeja_drive", headers=t.headers("responsable_legajos")).json()
    assert band["total"] == 4
    por_nombre = {i["nombre"]: i for i in band["items"]}
    assert por_nombre["persona_0042__Altura__2027-06-30.pdf"]["confianza"] == "media" and "ambiguo" in por_nombre["persona_0042__Altura__2027-06-30.pdf"]["motivo"]
    assert por_nombre["persona_9999__Apto_medico__2027-06-30.pdf"]["motivo"] == "sujeto inexistente"
    assert por_nombre["foto.jpg"]["motivo"] == "el nombre no sigue la convención"
    assert "no aceptado" in por_nombre["persona_0042__Apto_medico__2027-06-30.docx"]["motivo"]
    # re-escaneo: nada nuevo
    r2 = _ok(_post(cliente_api, t, "responsable_legajos", "escanear_drive", {"motivo": "otra vez"}))
    assert (r2["nuevos"], r2["ya_vistos"]) == (0, 6)
    # el responsable resuelve la ambigua a mano → importado; descarta otra
    amb = por_nombre["persona_0042__Altura__2027-06-30.pdf"]["archivo_drive_id"]
    with tenant_session(t.tenant_id) as s:
        altura = s.execute(text("SELECT requisito_definicion_id::text FROM modulo1.definicion_requisito WHERE tenant_id = :t AND nombre = 'Altura en andamios'"), {"t": t.tenant_id}).scalar()
    r3 = _post(cliente_api, t, "responsable_legajos", "resolver_archivo_drive", {"archivo_drive_id": amb, "sujeto_id": "persona_0042", "requisito_definicion_id": altura,
                                                                                  "vigente_desde": "2026-07-01", "vigente_hasta": "2027-06-30"})
    assert r3.status_code == 200, r3.text
    assert _post(cliente_api, t, "responsable_legajos", "resolver_archivo_drive", {"archivo_drive_id": amb, "sujeto_id": "persona_0042", "requisito_definicion_id": altura,
                                                                                    "vigente_desde": "2026-07-01", "vigente_hasta": "2027-06-30"}).status_code == 409
    assert _post(cliente_api, t, "responsable_legajos", "descartar_archivo_drive", {"archivo_drive_id": por_nombre["foto.jpg"]["archivo_drive_id"], "motivo": "no es evidencia"}).status_code == 200
    assert cliente_api.get("/v1/consultas/bandeja_drive", headers=t.headers("configuracion")).json()["total"] == 2
    cfg = cliente_api.get("/v1/consultas/configuracion_drive", headers=t.headers("responsable_legajos")).json()
    assert cfg["pendientes_revision"] == 2 and cfg["ultimo_escaneo_resultado"]["vistos"] == 6 and cfg["intervalo_horas"] == 6
    # lo importado sigue siendo una propuesta: no habilita hasta confirmar
    pend = cliente_api.get("/v1/consultas/propuestas_pendientes", headers=t.headers("responsable_legajos")).json()
    assert pend["total"] >= 2


def test_drive_escaneo_programado_por_el_worker(cliente_api, drive):
    t, prov, storage = drive["t"], drive["prov"], drive["storage"]
    _ok(_post(cliente_api, t, "configuracion", "configurar_drive", {"habilitado": True, "carpeta_id": "carpeta-1", "intervalo_horas": 6}))
    r = worker_main.correr_una_vuelta(storage, PublicadorEnMemoria(), ahora=T0, proveedor_drive=prov)
    with tenant_session(t.tenant_id) as s:
        cfg = s.execute(text("SELECT ultimo_escaneo_en, ultimo_escaneo_resultado FROM modulo1.configuracion_drive WHERE tenant_id = :t"), {"t": t.tenant_id}).one()
    assert cfg[0] == T0 and cfg[1]["importados"] == 2
    # antes del intervalo no vuelve a escanear; después sí
    worker_main.correr_una_vuelta(storage, PublicadorEnMemoria(), ahora=T0 + timedelta(hours=5), proveedor_drive=prov)
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT ultimo_escaneo_en FROM modulo1.configuracion_drive WHERE tenant_id = :t"), {"t": t.tenant_id}).scalar() == T0
    worker_main.correr_una_vuelta(storage, PublicadorEnMemoria(), ahora=T0 + timedelta(hours=7), proveedor_drive=prov)
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT ultimo_escaneo_en FROM modulo1.configuracion_drive WHERE tenant_id = :t"), {"t": t.tenant_id}).scalar() == T0 + timedelta(hours=7)


def test_drive_proveedor_no_disponible_es_422(cliente_api, drive, monkeypatch):
    from app.modules import capacidades_router as cr
    t = drive["t"]
    monkeypatch.setattr(cr, "_proveedor_drive", lambda: ProveedorEnMemoria())     # sin la carpeta
    monkeypatch.setattr(cr, "_storage", lambda: drive["storage"])
    _ok(_post(cliente_api, t, "configuracion", "configurar_drive", {"habilitado": True, "carpeta_id": "carpeta-1"}))
    r = _post(cliente_api, t, "responsable_legajos", "escanear_drive", {})
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "drive_no_disponible"


def test_google_drive_sin_credenciales_no_arranca(monkeypatch):
    from app.modules.drive.proveedor import GoogleDrive, ProveedorNoDisponible
    monkeypatch.delenv("DRIVE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("DRIVE_SERVICE_ACCOUNT_FILE", raising=False)
    with pytest.raises(ProveedorNoDisponible):
        GoogleDrive().listar("x")
