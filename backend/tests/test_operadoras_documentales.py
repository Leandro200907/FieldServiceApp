from __future__ import annotations

from sqlalchemy import text

from app.db import tenant_session
from tests import apoyo
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post


def _registrar(cliente, tenant, **cambios):
    body = {
        "operadora": "Operadora Norte",
        "sujeto_id": cambios.pop("sujeto_id"),
        "documento_id": cambios.pop("documento_id"),
        "estado": cambios.pop("estado"),
        "fuente_archivo": "estado_operadora.xlsx",
        "fuente_hoja": "Vehículos",
        "fuente_fila": 12,
        **cambios,
    }
    return _ok(_post(cliente, tenant, "responsable_legajos", "registrar_estado_documento_operadora", body))


def test_nueva_version_abre_alerta_por_operadora_y_aceptacion_la_cierra(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    sujeto = _alta_persona(cliente_api, t, "persona espejo")
    with tenant_session(t.tenant_id) as session:
        apoyo.supervisor_de(session, t, sujeto)

    anterior = _cargar(cliente_api, t, sujeto, req, desde="2026-01-01", hasta="2026-09-26")
    aceptado = _registrar(
        cliente_api, t, sujeto_id=sujeto, documento_id=anterior["documento_id"], estado="aceptado",
        exportado_en="2026-01-02T10:00:00Z", enviado_en="2026-01-02T11:00:00Z",
        aceptado_en="2026-01-03T09:00:00Z",
    )
    assert aceptado["alerta"] is None

    nuevo = _cargar(cliente_api, t, sujeto, req, desde="2026-09-27", hasta="2027-09-25")
    consulta = cliente_api.get("/v1/consultas/alertas_actualizacion_operadora", headers=t.headers("responsable_legajos"))
    assert consulta.status_code == 200
    alerta = consulta.json()["items"][0]
    assert consulta.json()["total"] == 1
    assert alerta["documento_vigente_id"] == nuevo["documento_id"]
    assert alerta["ultimo_documento_operadora_id"] == anterior["documento_id"]
    assert alerta["estado"] == "pendiente_envio"

    # Responsable + supervisor concreto reciben aviso; no se notifica a todos los supervisores.
    with tenant_session(t.tenant_id) as session:
        trabajos = session.execute(text(
            "SELECT payload FROM modulo1.job_queue WHERE cola = 'notificaciones' "
            "AND payload->>'tipo' = 'DocumentoOperadoraDesactualizado' ORDER BY id"
        )).scalars().all()
        assert [p["destinatario_rol"] for p in trabajos] == ["responsable_legajos", "supervisor"]
        assert trabajos[1]["destinatario_usuario_id"] == t.usuarios["supervisor"]

    enviado = _registrar(
        cliente_api, t, sujeto_id=sujeto, documento_id=nuevo["documento_id"], estado="enviado",
        exportado_en="2026-09-27T12:00:00Z", enviado_en="2026-09-27T12:10:00Z",
    )
    assert enviado["alerta"]["estado"] == "pendiente_aceptacion"

    cerrado = _registrar(
        cliente_api, t, sujeto_id=sujeto, documento_id=nuevo["documento_id"], estado="aceptado",
        aceptado_en="2026-09-28T09:00:00Z",
    )
    assert cerrado["alerta"] is None
    assert cliente_api.get("/v1/consultas/alertas_actualizacion_operadora", headers=t.headers("responsable_legajos")).json()["total"] == 0

    with tenant_session(t.tenant_id) as session:
        fuente = session.execute(text(
            "SELECT fuente_archivo, fuente_hoja, fuente_fila FROM modulo1.entrega_documento_operadora "
            "WHERE documento_id = :d"
        ), {"d": nuevo["documento_id"]}).mappings().one()
        assert dict(fuente) == {"fuente_archivo": "estado_operadora.xlsx", "fuente_hoja": "Vehículos", "fuente_fila": 12}


def test_supervisor_solo_ve_alertas_de_su_alcance(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Seguro")
    visible = _alta_persona(cliente_api, t, "visible")
    oculto = _alta_persona(cliente_api, t, "oculto")
    with tenant_session(t.tenant_id) as session:
        apoyo.supervisor_de(session, t, visible)
    for sujeto in (visible, oculto):
        anterior = _cargar(cliente_api, t, sujeto, req, desde="2026-01-01", hasta="2026-09-26")
        _registrar(cliente_api, t, sujeto_id=sujeto, documento_id=anterior["documento_id"], estado="aceptado")
        _cargar(cliente_api, t, sujeto, req, desde="2026-09-27", hasta="2027-09-25")

    responsable = cliente_api.get("/v1/consultas/alertas_actualizacion_operadora", headers=t.headers("responsable_legajos")).json()
    supervisor = cliente_api.get("/v1/consultas/alertas_actualizacion_operadora", headers=t.headers("supervisor")).json()
    assert responsable["total"] == 2
    assert supervisor["total"] == 1 and supervisor["items"][0]["sujeto_id"] == visible
