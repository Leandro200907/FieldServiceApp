"""Contrato de frontera: Módulo 1 informa cumplimiento, no opera asignaciones."""

from app.main import app


RUTAS_OPERATIVAS_RETIRADAS = {
    "/v1/comandos/cambiar_custodia",
    "/v1/comandos/corregir_custodia",
    "/v1/comandos/otorgar_excepcion",
    "/v1/comandos/revocar_excepcion",
    "/v1/comandos/registrar_constancia_del_cliente",
    "/v1/comandos/revocar_constancia_del_cliente",
    "/v1/comandos/evaluar_habilitacion",
    "/v1/comandos/asignar-supervisor",
    "/v1/comandos/reasignar-supervisor",
    "/v1/consultas/backlog_oc",
    "/v1/consultas/cobertura_oc",
    "/v1/consultas/decisiones_oc",
    "/v1/consultas/decision",
    "/v1/consultas/historial_supervision",
    "/v1/consultas/excepciones",
    "/v1/consultas/constancias",
    "/v1/consultas/custodias",
    "/v1/consultas/asignaciones_supervisor",
}


def test_openapi_no_expone_operaciones_que_pertenecen_al_modulo_2():
    rutas = set(app.openapi()["paths"])
    assert rutas.isdisjoint(RUTAS_OPERATIVAS_RETIRADAS)


def test_openapi_conserva_lectura_documental_y_radar_informativo():
    rutas = set(app.openapi()["paths"])
    assert {
        "/v1/consultas/legajo",
        "/v1/consultas/mi_legajo",
        "/v1/consultas/tablero_vencimientos",
        "/v1/consultas/calendario_vigencias",
        "/v1/consultas/radar_documental_backlog",
        "/v1/consultas/radar_documental_oc",
        "/v1/consultas/radar_documental_oc/{oc_id}/legajos/{sujeto_id}",
    } <= rutas
