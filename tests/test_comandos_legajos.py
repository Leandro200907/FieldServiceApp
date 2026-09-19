"""Comandos de Evidencia contra base real: legajos, documentos (sucesión, propuesta,
confirmación), lotes (idempotencia por lote_id, reversión), supervisores, permisos e
Idempotency-Key."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import text

from app.comun.reloj import hoy_del_tenant
from app.db import tenant_session

CMD = "/v1/comandos"


# --------------------------------------------------------------------------- helpers


def _post(cliente_api, tenant, rol: str, comando: str, body: dict, clave: str | None = None):
    return cliente_api.post(f"{CMD}/{comando}", json=body, headers=tenant.headers(rol, idempotency_key=clave))


def _ok(r) -> dict:
    assert r.status_code == 200, r.text
    return r.json()


def _alta_def(cliente_api, tenant, nombre: str, categoria: str = "documento", tipo: str = "persona", **extra) -> str:
    body = {"nombre": nombre, "categoria": categoria, "tipo_sujeto_aplicable": tipo, **extra}
    return _ok(_post(cliente_api, tenant, "configuracion", "dar_de_alta_definicion_de_requisito", body))["requisito_definicion_id"]


def _alta_persona(cliente_api, tenant, ident: str, sujeto_id: str | None = None) -> str:
    body = {"tipo_sujeto": "persona", "identificador_natural": ident}
    if sujeto_id:
        body["sujeto_id"] = sujeto_id
    return _ok(_post(cliente_api, tenant, "responsable_legajos", "alta_de_sujeto", body))["sujeto_id"]


def _cargar(cliente_api, tenant, sujeto_id: str, req: str, desde="2026-03-01", hasta="2026-09-15", **extra) -> dict:
    body = {"sujeto_id": sujeto_id, "requisito_definicion_id": req, "vigente_desde": desde, "vigente_hasta": hasta, **extra}
    return _ok(_post(cliente_api, tenant, "responsable_legajos", "cargar_documento", body))


def _docs(tenant, sujeto_id: str, req: str) -> list[dict]:
    with tenant_session(tenant.tenant_id) as s:
        filas = s.execute(
            text(
                "SELECT documento_id, estado_version, estado_confirmacion, version, origen_propuesta, sucede_a, lote_id "
                "FROM modulo1.documento WHERE sujeto_id = :sj AND requisito_definicion_id = :r ORDER BY version"
            ),
            {"sj": sujeto_id, "r": req},
        ).mappings().all()
        return [{k: (str(v) if v is not None and k in ("documento_id", "sucede_a", "lote_id") else v) for k, v in f.items()} for f in filas]


def _vigentes(docs: list[dict]) -> list[str]:
    return [d["documento_id"] for d in docs if d["estado_version"] == "vigente"]


def _eventos(tenant, tipo: str) -> int:
    with tenant_session(tenant.tenant_id) as s:
        return s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = :tipo"), {"tipo": tipo}).scalar()


# --------------------------------------------------------------------------- legajos


def test_alta_carga_y_sucesion_un_solo_vigente(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")

    r = _post(cliente_api, t, "responsable_legajos", "alta_de_sujeto", {"tipo_sujeto": "persona", "identificador_natural": "DNI 30111222"})
    alta = _ok(r)
    assert alta["sujeto_id"].startswith("persona_") and alta["eventos"] == ["LegajoCreado"]
    sujeto = alta["sujeto_id"]

    # identificador_natural único por tenant+tipo (mismo tipo → 409; otro tipo → ok)
    repetido = _post(cliente_api, t, "responsable_legajos", "alta_de_sujeto", {"tipo_sujeto": "persona", "identificador_natural": "DNI 30111222"})
    assert repetido.status_code == 409 and repetido.json()["error"]["codigo"] == "conflicto"
    _ok(_post(cliente_api, t, "responsable_legajos", "alta_de_sujeto", {"tipo_sujeto": "vehiculo", "identificador_natural": "DNI 30111222"}))

    d1 = _cargar(cliente_api, t, sujeto, req)
    assert d1["version"] == 1 and d1["sucede_a"] is None and d1["eventos"] == ["DocumentoCargado"]

    d2 = _cargar(cliente_api, t, sujeto, req, desde="2026-09-01", hasta="2027-03-01", numero="AM-2")
    assert d2["version"] == 2 and d2["sucede_a"] == d1["documento_id"]
    assert d2["eventos"] == ["DocumentoCargado", "DocumentoSucedido"]

    docs = _docs(t, sujeto, req)
    assert [d["estado_version"] for d in docs] == ["sucedida", "vigente"]
    assert _vigentes(docs) == [d2["documento_id"]]
    assert docs[1]["estado_confirmacion"] == "verificado"  # default cuando carga el responsable
    assert _eventos(t, "DocumentoSucedido") == 1

    # requisito que no aplica al tipo de sujeto → error de dominio
    req_vehiculo = _alta_def(cliente_api, t, "VTV", tipo="vehiculo")
    no_aplica = _post(cliente_api, t, "responsable_legajos", "cargar_documento",
                      {"sujeto_id": sujeto, "requisito_definicion_id": req_vehiculo, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"})
    assert no_aplica.status_code == 422 and no_aplica.json()["error"]["codigo"] == "regla_de_dominio"

    # vigencia invertida → 422 de dominio (antes de tocar el CHECK)
    invertida = _post(cliente_api, t, "responsable_legajos", "cargar_documento",
                      {"sujeto_id": sujeto, "requisito_definicion_id": req, "vigente_desde": "2026-12-31", "vigente_hasta": "2026-01-01"})
    assert invertida.status_code == 422


def test_baja_de_sujeto(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    sujeto = _alta_persona(cliente_api, t, "DNI 1")
    baja = _ok(_post(cliente_api, t, "responsable_legajos", "baja_de_sujeto", {"sujeto_id": sujeto}))
    assert baja["eventos"] == ["LegajoDadoDeBaja"]
    otra_vez = _post(cliente_api, t, "responsable_legajos", "baja_de_sujeto", {"sujeto_id": sujeto})
    assert otra_vez.status_code == 409
    inexistente = _post(cliente_api, t, "responsable_legajos", "baja_de_sujeto", {"sujeto_id": "persona_nadie"})
    assert inexistente.status_code == 404
    # sobre un sujeto dado de baja no se carga nada
    r = _post(cliente_api, t, "responsable_legajos", "cargar_documento",
              {"sujeto_id": sujeto, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"})
    assert r.status_code == 409
    # el identificador vuelve a estar disponible para un alta nueva
    _alta_persona(cliente_api, t, "DNI 1")


# --------------------------------------------------------------------------- permisos


def test_permisos_supervisor_no_puede_cargar_documento(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    sujeto = _alta_persona(cliente_api, t, "DNI 2")
    body = {"sujeto_id": sujeto, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"}
    for rol in ("supervisor", "tecnico", "configuracion"):
        r = _post(cliente_api, t, rol, "cargar_documento", body)
        assert r.status_code == 403, rol
        assert r.json() == {"error": {"codigo": "prohibido", "mensaje": r.json()["error"]["mensaje"], "detalles": {"roles_requeridos": ["responsable_legajos"]}}}
    assert _docs(t, sujeto, req) == []
    sin_token = cliente_api.post(f"{CMD}/cargar_documento", json=body)
    assert sin_token.status_code == 401 and sin_token.json()["error"]["codigo"] == "no_autenticado"


# --------------------------------------------------------------------------- propuestas


def test_propuesta_y_rechazo_restaura_el_anterior(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    propio = _alta_persona(cliente_api, t, "DNI técnico", sujeto_id=t.sujeto_tecnico)
    ajeno = _alta_persona(cliente_api, t, "DNI otro")
    d1 = _cargar(cliente_api, t, propio, req)

    body = {"sujeto_id": propio, "requisito_definicion_id": req, "vigente_desde": "2026-09-01", "vigente_hasta": "2027-09-01"}
    # solo sobre su propio legajo
    ajena = _post(cliente_api, t, "tecnico", "proponer_documento", {**body, "sujeto_id": ajeno})
    assert ajena.status_code == 403
    # el responsable no propone, carga
    assert _post(cliente_api, t, "responsable_legajos", "proponer_documento", body).status_code == 403

    prop = _ok(_post(cliente_api, t, "tecnico", "proponer_documento", body))
    assert prop["sucede_a"] == d1["documento_id"] and prop["eventos"] == ["DocumentoCargado", "DocumentoSucedido"]
    docs = _docs(t, propio, req)
    assert _vigentes(docs) == [prop["documento_id"]]
    assert docs[1]["origen_propuesta"] is True and docs[1]["estado_confirmacion"] == "declarado"
    assert docs[0]["estado_version"] == "sucedida"

    # rechazar: la propuesta queda `rechazada` (terminal) y d1 vuelve a `vigente`
    rech = _ok(_post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": prop["documento_id"], "motivo": "foto ilegible"}))
    assert rech["restaurado_documento_id"] == d1["documento_id"] and rech["eventos"] == ["DocumentoRechazado"]
    docs = _docs(t, propio, req)
    assert {d["documento_id"]: d["estado_version"] for d in docs} == {d1["documento_id"]: "vigente", prop["documento_id"]: "rechazada"}

    # terminal: no se vuelve a rechazar ni a confirmar
    assert _post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": prop["documento_id"]}).status_code == 409
    assert _post(cliente_api, t, "responsable_legajos", "confirmar_documento", {"documento_id": prop["documento_id"]}).status_code == 409
    # un documento cargado (no propuesta) no se rechaza
    assert _post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": d1["documento_id"]}).status_code == 409

    # propuesta sobre un requisito sin documento previo: queda vigente sin sucesión
    req2 = _alta_def(cliente_api, t, "Carnet de conducir")
    sola = _ok(_post(cliente_api, t, "tecnico", "proponer_documento", {**body, "requisito_definicion_id": req2}))
    assert sola["sucede_a"] is None and sola["eventos"] == ["DocumentoCargado"]
    rech2 = _ok(_post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": sola["documento_id"]}))
    assert rech2["restaurado_documento_id"] is None
    assert _vigentes(_docs(t, propio, req2)) == []


# --------------------------------------------------------------------------- confirmación


def test_confirmar_documento_regulariza_excepcion(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Trabajo en altura")
    otro_req = _alta_def(cliente_api, t, "Apto médico")
    sujeto = _alta_persona(cliente_api, t, "DNI 42")
    otro_sujeto = _alta_persona(cliente_api, t, "DNI 43")

    # Excepciones otorgadas: una sobre (sujeto, req) que debe regularizarse; otras que no.
    with tenant_session(t.tenant_id) as s:
        for sj, r, estado in ((sujeto, req, "otorgada"), (sujeto, req, "revocada"), (sujeto, otro_req, "otorgada"), (otro_sujeto, req, "otorgada")):
            s.execute(
                text(
                    "INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, commitment_id, "
                    "otorgada_por, motivo, estado) VALUES (:t, :ev, :sj, :r, 'compromiso_OC-2026-1188', 'sup', 'prueba', :estado)"
                ),
                {"t": t.tenant_id, "ev": str(uuid.uuid4()), "sj": sj, "r": r, "estado": estado},
            )

    d = _cargar(cliente_api, t, sujeto, req, estado_confirmacion="declarado")
    assert _docs(t, sujeto, req)[0]["estado_confirmacion"] == "declarado"

    conf = _ok(_post(cliente_api, t, "responsable_legajos", "confirmar_documento", {"documento_id": d["documento_id"]}))
    assert conf["eventos"] == ["DocumentoVerificado", "ExcepcionRegularizada"]
    assert len(conf["excepciones_regularizadas"]) == 1
    assert _docs(t, sujeto, req)[0]["estado_confirmacion"] == "verificado"
    with tenant_session(t.tenant_id) as s:
        estados = s.execute(text("SELECT sujeto_id, requisito_definicion_id::text, estado FROM modulo1.excepcion")).all()
        assert sorted(tuple(e) for e in estados) == sorted([
            (sujeto, req, "regularizada"), (sujeto, req, "revocada"), (sujeto, otro_req, "otorgada"), (otro_sujeto, req, "otorgada"),
        ])
    assert _eventos(t, "ExcepcionRegularizada") == 1 and _eventos(t, "DocumentoVerificado") == 1

    # ya verificado: no se confirma dos veces
    assert _post(cliente_api, t, "responsable_legajos", "confirmar_documento", {"documento_id": d["documento_id"]}).status_code == 409
    assert _post(cliente_api, t, "responsable_legajos", "confirmar_documento", {"documento_id": str(uuid.uuid4())}).status_code == 404


# --------------------------------------------------------------------------- competencia / inducción


def test_acreditacion_e_induccion(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    loc = str(uuid.uuid4())
    req_doc = _alta_def(cliente_api, t, "Certificado altura")
    req_comp = _alta_def(cliente_api, t, "Trabajo en altura", "competencia")
    req_ind = _alta_def(cliente_api, t, "Inducción yacimiento", "induccion", locacion_id=loc)
    sujeto = _alta_persona(cliente_api, t, "DNI 7")
    otro = _alta_persona(cliente_api, t, "DNI 8")
    evidencia = _cargar(cliente_api, t, sujeto, req_doc)["documento_id"]

    base = {"persona_id": sujeto, "vigente_desde": "2026-03-01", "vigente_hasta": "2027-03-01"}
    acr = _ok(_post(cliente_api, t, "responsable_legajos", "registrar_acreditacion_de_competencia",
                    {**base, "requisito_definicion_id": req_comp, "evidencias": [evidencia]}))
    assert acr["eventos"] == ["AcreditacionDeCompetenciaRegistrada"]
    # evidencia de otro sujeto → 404; categoría equivocada → 422; sin evidencias → 422 validación
    assert _post(cliente_api, t, "responsable_legajos", "registrar_acreditacion_de_competencia",
                 {**base, "persona_id": otro, "requisito_definicion_id": req_comp, "evidencias": [evidencia]}).status_code == 404
    assert _post(cliente_api, t, "responsable_legajos", "registrar_acreditacion_de_competencia",
                 {**base, "requisito_definicion_id": req_doc, "evidencias": [evidencia]}).status_code == 422
    assert _post(cliente_api, t, "responsable_legajos", "registrar_acreditacion_de_competencia",
                 {**base, "requisito_definicion_id": req_comp, "evidencias": []}).status_code == 422

    ind = _ok(_post(cliente_api, t, "responsable_legajos", "registrar_induccion",
                    {**base, "locacion_id": loc, "requisito_definicion_id": req_ind, "evidencia": evidencia}))
    assert ind["eventos"] == ["InduccionRegistrada"]
    otra_loc = _post(cliente_api, t, "responsable_legajos", "registrar_induccion",
                     {**base, "locacion_id": str(uuid.uuid4()), "requisito_definicion_id": req_ind, "evidencia": evidencia})
    assert otra_loc.status_code == 422

    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.acreditacion_competencia")).scalar() == 1
        assert s.execute(text("SELECT count(*) FROM modulo1.induccion WHERE locacion_id = :l"), {"l": loc}).scalar() == 1


# --------------------------------------------------------------------------- lotes


def test_importar_lote_idempotente_por_lote_id(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    s1 = _alta_persona(cliente_api, t, "DNI 11")
    s2 = _alta_persona(cliente_api, t, "DNI 12")
    lote_id = str(uuid.uuid4())
    body = {
        "lote_id": lote_id, "origen": "planilla",
        "filas": [
            {"sujeto_id": s1, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"},
            {"sujeto_id": s2, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31", "estado_confirmacion": "verificado"},
            {"sujeto_id": "persona_no_existe", "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"},
            {"sujeto_id": s1, "requisito_definicion_id": str(uuid.uuid4()), "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"},
        ],
    }
    assert _post(cliente_api, t, "supervisor", "importar_lote", body).status_code == 403

    r1 = _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", body))
    assert (r1["filas_totales"], r1["filas_aceptadas"], r1["filas_rechazadas"]) == (4, 2, 2)
    assert [f["fila"] for f in r1["detalle_filas_rechazadas"]] == [2, 3]
    assert r1["detalle_filas_rechazadas"][0]["codigo"] == "no_encontrado"
    assert r1["eventos"] == ["DocumentoCargado", "DocumentoCargado", "LoteAplicado"]
    assert _docs(t, s1, req)[0]["estado_confirmacion"] == "declarado"  # default del lote
    assert _docs(t, s2, req)[0]["estado_confirmacion"] == "verificado"
    assert _docs(t, s1, req)[0]["lote_id"] == lote_id

    # Mismo lote_id con filas distintas: 409 (A-03), nada nuevo. Mismo contenido: replay exacto.
    r_dist = _post(cliente_api, t, "responsable_legajos", "importar_lote", {**body, "filas": body["filas"][:1]})
    assert r_dist.status_code == 409 and r_dist.json()["error"]["codigo"] == "clave_idempotencia_reutilizada"
    r2 = _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", body))
    assert r2 == r1
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.documento")).scalar() == 2
        assert s.execute(text("SELECT count(*) FROM modulo1.lote_importacion")).scalar() == 1
        lote = s.execute(text("SELECT estado, filas_totales, filas_aceptadas, filas_rechazadas FROM modulo1.lote_importacion")).first()
        assert tuple(lote) == ("aplicado", 4, 2, 2)
        # aunque venza el registro de idempotencia, el lote existente no se re-aplica
        s.execute(text("DELETE FROM modulo1.idempotency_keys"))
    r3 = _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", body))
    assert r3["ya_aplicado"] is True and r3["filas_aceptadas"] == 2
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.documento")).scalar() == 2
    assert _eventos(t, "LoteAplicado") == 1


def test_revertir_lote_restaura_los_vigentes_anteriores(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    s1 = _alta_persona(cliente_api, t, "DNI 21")
    s2 = _alta_persona(cliente_api, t, "DNI 22")
    manual = _cargar(cliente_api, t, s1, req)  # s1 ya tenía un documento; s2 no
    lote_id = str(uuid.uuid4())
    filas = [
        {"sujeto_id": s1, "requisito_definicion_id": req, "vigente_desde": "2026-06-01", "vigente_hasta": "2027-06-01"},
        {"sujeto_id": s2, "requisito_definicion_id": req, "vigente_desde": "2026-06-01", "vigente_hasta": "2027-06-01"},
    ]
    r = _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", {"lote_id": lote_id, "origen": "drive", "filas": filas}))
    assert _docs(t, s1, req)[0]["estado_version"] == "sucedida"

    # Uno de los documentos del lote fue sucedido después por una carga manual: esa carga
    # posterior sigue vigente y no se resucita nada por debajo de ella.
    posterior = _cargar(cliente_api, t, s2, req, desde="2026-08-01", hasta="2027-08-01")

    rev = _ok(_post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": lote_id}))
    assert rev["eventos"] == ["LoteRevertido"]
    assert sorted(rev["documentos_revertidos"]) == sorted(d["documento_id"] for d in r["documentos"])
    assert rev["documentos_restaurados"] == [manual["documento_id"]]

    docs_s1 = _docs(t, s1, req)
    assert {d["documento_id"]: d["estado_version"] for d in docs_s1} == {manual["documento_id"]: "vigente", r["documentos"][0]["documento_id"]: "revertida_por_lote"}
    docs_s2 = _docs(t, s2, req)
    assert {d["documento_id"]: d["estado_version"] for d in docs_s2} == {r["documentos"][1]["documento_id"]: "revertida_por_lote", posterior["documento_id"]: "vigente"}

    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT estado FROM modulo1.lote_importacion WHERE lote_id = :l"), {"l": lote_id}).scalar() == "revertido"
    assert _post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": lote_id}).status_code == 409
    assert _post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": str(uuid.uuid4())}).status_code == 404


# --------------------------------------------------------------------------- Idempotency-Key


def test_idempotency_key_repite_respuesta_sin_duplicar(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    body = {"tipo_sujeto": "equipo", "identificador_natural": "SERIE-001"}
    r1 = _ok(_post(cliente_api, t, "responsable_legajos", "alta_de_sujeto", body, clave="alta-equipo-1"))
    r2 = _ok(_post(cliente_api, t, "responsable_legajos", "alta_de_sujeto", body, clave="alta-equipo-1"))
    assert r1 == r2
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.legajo")).scalar() == 1
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = 'LegajoCreado'")).scalar() == 1
    # sin clave (u otra clave) el mismo body choca con la unicidad del identificador
    assert _post(cliente_api, t, "responsable_legajos", "alta_de_sujeto", body, clave="alta-equipo-2").status_code == 409


# --------------------------------------------------------------------------- supervisor


def test_asignar_y_reasignar_supervisor(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    sujeto = _alta_persona(cliente_api, t, "DNI 31")
    sup = t.usuarios["supervisor"]
    no_sup = t.usuarios["tecnico"]
    with tenant_session(t.tenant_id) as s:
        hoy = hoy_del_tenant(s, t.tenant_id)

    # técnico y supervisor no asignan; configuración y responsable sí
    assert _post(cliente_api, t, "supervisor", "asignar_supervisor", {"sujeto_id": sujeto, "supervisor_usuario_id": sup}).status_code == 403
    # el usuario destino tiene que ser supervisor
    r = _post(cliente_api, t, "configuracion", "asignar_supervisor", {"sujeto_id": sujeto, "supervisor_usuario_id": no_sup})
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "regla_de_dominio"
    assert _post(cliente_api, t, "configuracion", "asignar_supervisor", {"sujeto_id": sujeto, "supervisor_usuario_id": str(uuid.uuid4())}).status_code == 404

    a1 = _ok(_post(cliente_api, t, "configuracion", "asignar_supervisor", {"sujeto_id": sujeto, "supervisor_usuario_id": sup}))
    assert a1["desde"] == hoy.isoformat() and a1["eventos"] == ["SupervisorAsignado"]
    # ya hay una vigente → hay que reasignar
    assert _post(cliente_api, t, "responsable_legajos", "asignar_supervisor", {"sujeto_id": sujeto, "supervisor_usuario_id": sup}).status_code == 409

    # reasignar el mismo día que empezó la vigente no cierra nada coherente → 422
    assert _post(cliente_api, t, "responsable_legajos", "reasignar_supervisor",
                 {"sujeto_id": sujeto, "supervisor_usuario_id": sup, "desde": hoy.isoformat()}).status_code == 422

    manana = hoy + timedelta(days=1)
    a2 = _ok(_post(cliente_api, t, "responsable_legajos", "reasignar_supervisor",
                   {"sujeto_id": sujeto, "supervisor_usuario_id": sup, "desde": manana.isoformat()}))
    assert a2["asignacion_cerrada_id"] == a1["asignacion_id"] and a2["hasta_anterior"] == hoy.isoformat()
    assert a2["eventos"] == ["SupervisorReasignado"]

    with tenant_session(t.tenant_id) as s:
        filas = s.execute(
            text("SELECT asignacion_id::text, estado, desde::text, hasta::text, asignada_por FROM modulo1.asignacion_supervisor ORDER BY creado_en")
        ).all()
        assert [tuple(f) for f in filas] == [
            (a1["asignacion_id"], "cerrada", hoy.isoformat(), hoy.isoformat(), t.usuarios["configuracion"]),
            (a2["asignacion_id"], "vigente", manana.isoformat(), None, t.usuarios["responsable_legajos"]),
        ]
    # sin vigente no se reasigna
    otro = _alta_persona(cliente_api, t, "DNI 32")
    assert _post(cliente_api, t, "configuracion", "reasignar_supervisor", {"sujeto_id": otro, "supervisor_usuario_id": sup}).status_code == 409
