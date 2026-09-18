"""Flujo completo por HTTP (paso 5 de la retoma): sin SQL directo, solo comandos y consultas
reales encadenados, reproduciendo los casos de oro 6.1, 6.3 y 6.5 de punta a punta y la
invariante "una excepción nunca vuelve verde".

Fechas relativas a `hoy` del tenant (zona horaria America/Argentina/Buenos_Aires), que se
obtiene por la misma vía que usa la app (reloj del tenant), no por date.today().
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from app.comun.reloj import hoy_del_tenant
from app.db import tenant_session


def _ok(r, status=200):
    assert r.status_code == status, (r.status_code, r.text)
    return r.json()


def test_flujo_completo_por_http(cliente_api, tenant_de_prueba):
    c, t = cliente_api, tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        hoy = hoy_del_tenant(s, t.tenant_id)
    d = lambda n: (hoy + timedelta(days=n)).isoformat()  # noqa: E731

    resp = t.headers("responsable_legajos")
    conf = t.headers("configuracion")
    sup = t.headers("supervisor")

    # --- Legajos: empresa + técnico (el técnico del conftest, con su sujeto_id vinculado)
    _ok(c.post("/v1/comandos/alta_de_sujeto", json={"tipo_sujeto": "empresa", "identificador_natural": "30-1"}, headers=resp))
    persona = _ok(c.post(
        "/v1/comandos/alta_de_sujeto",
        json={"tipo_sujeto": "persona", "identificador_natural": "DNI-42", "sujeto_id": t.sujeto_tecnico},
        headers=resp,
    ))["sujeto_id"]

    # --- Catálogo local (configuracion) y matriz v1: apto médico excepcionable
    req = _ok(c.post(
        "/v1/comandos/dar_de_alta_definicion_de_requisito",
        json={"nombre": "Apto médico", "categoria": "documento", "tipo_sujeto_aplicable": "persona"},
        headers=conf,
    ))["requisito_definicion_id"]
    cliente_id, locacion_id, tipo_servicio_id = (str(uuid.uuid4()) for _ in range(3))
    matriz = {"cliente_id": cliente_id, "locacion_id": locacion_id, "tipo_servicio_id": tipo_servicio_id}
    v1 = _ok(c.post(
        "/v1/comandos/publicar_version_de_matriz",
        json={**matriz, "vigente_desde": d(-30),
              "lineas": [{"requisito_definicion_id": req, "clasificacion": "excepcionable", "bloqueante_durante_ejecucion": True}]},
        headers=conf,
    ))
    assert v1["version"] == 1

    # --- Permisos: el supervisor NO puede cargar documentos (exclusivo de responsable)
    r = c.post("/v1/comandos/cargar_documento", json={"sujeto_id": persona, "requisito_definicion_id": req,
                                                       "vigente_desde": d(-100), "vigente_hasta": d(10)}, headers=sup)
    assert r.status_code == 403 and r.json()["error"]["codigo"] == "prohibido"

    # --- Documento vigente hasta hoy+10 (borde inclusive, 6.1)
    _ok(c.post("/v1/comandos/cargar_documento", json={"sujeto_id": persona, "requisito_definicion_id": req,
                                                        "vigente_desde": d(-100), "vigente_hasta": d(10)}, headers=resp))

    # --- Backlog de OC: una termina justo el día que vence el documento, la otra un día después
    lote = _ok(c.post("/v1/comandos/importar_lote_oc", json={
        "lote_id": str(uuid.uuid4()), "origen": "planilla",
        "filas": [
            {"clave_origen": "OC-BORDE", **matriz, "vigencia_desde": d(0), "vigencia_hasta": d(10)},
            {"clave_origen": "OC-PASADA", **matriz, "vigencia_desde": d(0), "vigencia_hasta": d(11)},
        ]}, headers=resp))
    assert lote["filas_aceptadas"] == 2, lote

    # 6.1: vigente_hasta inclusive → habilitado el mismo día, vence_durante_el_trabajo al siguiente
    ev_borde = _ok(c.post("/v1/comandos/evaluar_habilitacion", json={"commitment_id": "OC-BORDE"}, headers=sup))
    assert ev_borde["veredicto_de_cumplimiento"] == "habilitado"
    assert ev_borde["resultado_de_decision"] == "puede_asignarse"
    ev_pasada = _ok(c.post("/v1/comandos/evaluar_habilitacion", json={"commitment_id": "OC-PASADA"}, headers=sup))
    assert ev_pasada["veredicto_de_cumplimiento"] == "vence_durante_el_trabajo"
    assert ev_pasada["resultado_de_decision"] == "no_puede_asignarse"

    # --- Excepción del supervisor sobre el requisito excepcionable: NUNCA vuelve verde
    exc = _ok(c.post("/v1/comandos/otorgar_excepcion", json={
        "referencia_evaluacion": ev_pasada["referencia_evaluacion"], "sujeto_id": persona,
        "requisito_definicion_id": req, "commitment_id": "OC-PASADA", "motivo": "renueva en 3 días"}, headers=sup))
    assert exc["excepcion_id"]
    ev_exc = _ok(c.post("/v1/comandos/evaluar_habilitacion", json={"commitment_id": "OC-PASADA"}, headers=sup))
    assert ev_exc["resultado_de_decision"] == "puede_asignarse_bajo_excepcion"
    assert ev_exc["veredicto_de_cumplimiento"] == "vence_durante_el_trabajo"  # no "habilitado"

    # Constancia sobre un requisito excepcionable se rechaza (solo aplica a bloqueante_duro)
    r = c.post("/v1/comandos/registrar_constancia_del_cliente", json={
        "sujeto_id": persona, "requisito_definicion_id": req, "cliente_id": cliente_id,
        "commitment_id": "OC-PASADA", "evidencia": "mail del cliente"}, headers=resp)
    assert r.status_code == 422, r.text

    # 6.3: versión insertada en el pasado → 409; versión vigente desde hoy → acepta y autocierra v1
    r = c.post("/v1/comandos/publicar_version_de_matriz", json={
        **matriz, "vigente_desde": d(-45),
        "lineas": [{"requisito_definicion_id": req, "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True}]},
        headers=conf)
    assert r.status_code == 409, r.text
    v2 = _ok(c.post("/v1/comandos/publicar_version_de_matriz", json={
        **matriz, "vigente_desde": d(0),
        "lineas": [{"requisito_definicion_id": req, "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True}]},
        headers=conf))
    assert v2["version"] == 2
    ayer = _ok(c.get("/v1/consultas/matriz_vigente", params={**matriz, "fecha": d(-1)}, headers=resp))
    hoy_m = _ok(c.get("/v1/consultas/matriz_vigente", params={**matriz, "fecha": d(0)}, headers=resp))
    assert ayer["version"] == 1 and ayer["vigente_hasta"] == d(-1)
    assert hoy_m["version"] == 2

    # 6.5: reclasificado a bloqueante_duro → la excepción sigue otorgada pero sin efecto
    ev_reclas = _ok(c.post("/v1/comandos/evaluar_habilitacion", json={"commitment_id": "OC-PASADA"}, headers=sup))
    assert ev_reclas["resultado_de_decision"] == "no_puede_asignarse"
    reqs = [r for sj in ev_reclas["por_sujeto"] if sj["sujeto_id"] == persona for r in sj["requisitos"]]
    assert any(r.get("excepcion_aplicable_pero_sin_efecto") for r in reqs), reqs
    # y una nueva excepción sobre bloqueante_duro se rechaza
    r = c.post("/v1/comandos/otorgar_excepcion", json={
        "referencia_evaluacion": ev_reclas["referencia_evaluacion"], "sujeto_id": persona,
        "requisito_definicion_id": req, "commitment_id": "OC-PASADA", "motivo": "x"}, headers=sup)
    assert r.status_code in (409, 422), r.text

    # Ahora sí: la constancia del cliente (bloqueante_duro) cubre el requisito
    _ok(c.post("/v1/comandos/registrar_constancia_del_cliente", json={
        "sujeto_id": persona, "requisito_definicion_id": req, "cliente_id": cliente_id,
        "commitment_id": "OC-PASADA", "evidencia": "constancia firmada por el cliente"}, headers=resp))
    ev_const = _ok(c.post("/v1/comandos/evaluar_habilitacion", json={"commitment_id": "OC-PASADA"}, headers=sup))
    assert ev_const["veredicto_de_cumplimiento"] == "habilitado"
    assert ev_const["resultado_de_decision"] == "puede_asignarse"

    # --- Lecturas: el técnico ve su propio legajo, la auditoría tiene los eventos del flujo
    legajo = _ok(c.get("/v1/consultas/legajo", params={"sujeto_id": persona}, headers=t.headers("tecnico")))
    assert legajo["documentos"][0]["vigente_hoy"] is True
    log = _ok(c.get("/v1/consultas/log_auditoria", params={"limit": 500}, headers=conf))
    tipos = {e["tipo"] for e in log["items"]}
    assert {"LegajoCreado", "DocumentoCargado", "MatrizVersionPublicada", "LoteAplicado",
            "EvaluacionDeHabilitacionRealizada", "ExcepcionOtorgada", "ConstanciaRegistrada"} <= tipos
