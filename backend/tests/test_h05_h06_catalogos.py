"""H-05: alcance del técnico incluye los recursos bajo su custodia vigente y `mi_legajo`
compuesto. H-06: consultas auxiliares para operar todos los comandos sin tipear ids —
permisos por rol, alcance multi-tenant, paginación y búsqueda."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.db import tenant_session
from tests import apoyo
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post


@pytest.fixture
def mundo(cliente_api, tenant_de_prueba):
    """Técnico con persona propia, un vehículo bajo su custodia, otro vehículo ajeno; otra
    persona fuera del universo del supervisor; documentos en todos."""
    t = tenant_de_prueba
    req_p = _alta_def(cliente_api, t, "Apto médico")
    req_v = _alta_def(cliente_api, t, "VTV", tipo="vehiculo")
    yo = t.sujeto_tecnico
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, yo)
        apoyo.supervisor_de(s, t, yo)
        for v in ("vehiculo_MIO", "vehiculo_AJENO"):
            apoyo.legajo(s, t.tenant_id, v, "vehiculo")
        apoyo.legajo(s, t.tenant_id, "persona_otra")
    otra = "persona_otra"
    r = _post(cliente_api, t, "supervisor", "cambiar_custodia", {"recurso_id": "vehiculo_MIO", "tipo_recurso": "vehiculo", "custodio_id": yo, "desde": "2026-01-01"})
    assert r.status_code == 200, r.text
    _cargar(cliente_api, t, yo, req_p, hasta="2027-06-30")
    _cargar(cliente_api, t, "vehiculo_MIO", req_v, hasta="2027-03-31")
    _cargar(cliente_api, t, "vehiculo_AJENO", req_v, hasta="2027-03-31")
    _cargar(cliente_api, t, otra, req_p, hasta="2027-06-30")
    return {"t": t, "yo": yo, "otra": otra, "req_p": req_p, "req_v": req_v, "periodo": r.json()["periodo_id"]}


def _get(cliente_api, t, como, ruta, **params):
    return cliente_api.get(f"/v1/consultas/{ruta}", params=params, headers=t.headers(como))


# --------------------------------------------------------------------------- H-05


def test_tecnico_ve_su_persona_y_sus_recursos_custodiados_nada_mas(cliente_api, mundo):
    t, yo = mundo["t"], mundo["yo"]
    assert _get(cliente_api, t, "tecnico", "legajo", sujeto_id=yo).status_code == 200
    assert _get(cliente_api, t, "tecnico", "legajo", sujeto_id="vehiculo_MIO").status_code == 200       # bajo su custodia
    assert _get(cliente_api, t, "tecnico", "legajo", sujeto_id="vehiculo_AJENO").status_code == 403     # de otro
    assert _get(cliente_api, t, "tecnico", "legajo", sujeto_id=mundo["otra"]).status_code == 403        # otra persona, nunca
    lista = _get(cliente_api, t, "tecnico", "sujetos").json()
    assert {i["sujeto_id"] for i in lista["items"]} == {yo, "vehiculo_MIO"} and lista["total"] == 2


def test_mi_legajo_compuesto_solo_para_tecnico(cliente_api, mundo):
    t, yo = mundo["t"], mundo["yo"]
    r = _get(cliente_api, t, "tecnico", "mi_legajo")
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["persona"]["legajo"]["sujeto_id"] == yo and len(c["persona"]["documentos"]) == 1
    assert [x["legajo"]["sujeto_id"] for x in c["recursos_bajo_custodia"]] == ["vehiculo_MIO"]
    rec = c["recursos_bajo_custodia"][0]
    assert rec["tipo_recurso"] == "vehiculo" and rec["periodo_id"] == mundo["periodo"] and len(rec["documentos"]) == 1
    assert c["resumen"]["vigentes_hoy"] == 2 and "vehiculo_AJENO" not in r.text and mundo["otra"] not in r.text
    for rol in ("supervisor", "responsable_legajos", "configuracion"):
        assert _get(cliente_api, t, rol, "mi_legajo").status_code == 403
    # la custodia cambia de manos → el vehículo sale de mi legajo y de mi alcance
    with tenant_session(t.tenant_id) as s:
        apoyo.supervisor_de(s, t, mundo["otra"])
    assert _post(cliente_api, t, "supervisor", "cambiar_custodia", {"recurso_id": "vehiculo_MIO", "tipo_recurso": "vehiculo", "custodio_id": mundo["otra"], "desde": "2026-06-01"}).status_code == 200
    assert _get(cliente_api, t, "tecnico", "mi_legajo").json()["recursos_bajo_custodia"] == []
    assert _get(cliente_api, t, "tecnico", "legajo", sujeto_id="vehiculo_MIO").status_code == 403


def test_tecnico_sin_sujeto_o_sin_legajo_no_tiene_mi_legajo(cliente_api, tenant_de_prueba):
    from app.api.errores import Prohibido
    from app.auth.identidad import Identidad, Rol
    from app.modules.consultas.catalogos import mi_legajo
    t = tenant_de_prueba
    # técnico cuyo legajo todavía no fue importado: 404 (no 500)
    assert _get(cliente_api, t, "tecnico", "mi_legajo").status_code == 404
    # identidad técnica sin sujeto_id: prohibido
    with tenant_session(t.tenant_id) as s, pytest.raises(Prohibido):
        mi_legajo(s, Identidad(t.tenant_id, t.usuarios["tecnico"], frozenset({Rol.TECNICO}), None))


# --------------------------------------------------------------------------- H-06: permisos y alcance


PERMISOS = {
    # ruta: (roles con 200, roles con 403)
    "sujetos": (("configuracion", "responsable_legajos", "supervisor", "tecnico"), ()),
    "definiciones_requisito": (("configuracion", "responsable_legajos", "supervisor", "tecnico"), ()),
    "matrices": (("configuracion", "responsable_legajos", "supervisor"), ("tecnico",)),
    "usuarios": (("configuracion", "responsable_legajos"), ("supervisor", "tecnico")),
    "documentos": (("configuracion", "responsable_legajos", "supervisor", "tecnico"), ()),
    "excepciones": (("configuracion", "responsable_legajos", "supervisor"), ("tecnico",)),
    "constancias": (("configuracion", "responsable_legajos", "supervisor"), ("tecnico",)),
    "custodias": (("configuracion", "responsable_legajos", "supervisor", "tecnico"), ()),
    "lotes": (("configuracion", "responsable_legajos"), ("supervisor", "tecnico")),
    "asignaciones_supervisor": (("configuracion", "responsable_legajos", "supervisor"), ("tecnico",)),
}


@pytest.mark.parametrize("ruta", sorted(PERMISOS))
def test_permisos_por_rol_y_forma_paginada(cliente_api, mundo, ruta):
    t = mundo["t"]
    ok, prohibidos = PERMISOS[ruta]
    for rol in ok:
        r = _get(cliente_api, t, rol, ruta, limit=2)
        assert r.status_code == 200, (ruta, rol, r.text)
        assert {"items", "total", "offset", "limit"} <= set(r.json()) and r.json()["limit"] == 2 and len(r.json()["items"]) <= 2
    for rol in prohibidos:
        assert _get(cliente_api, t, rol, ruta).status_code == 403, (ruta, rol)
    assert cliente_api.get(f"/v1/consultas/{ruta}").status_code == 401


def test_alcance_por_rol_en_listas_de_sujetos_documentos_y_custodias(cliente_api, mundo):
    t, yo, otra = mundo["t"], mundo["yo"], mundo["otra"]
    # responsable: todo el tenant; supervisor: su universo (yo + vehiculo_MIO); técnico: yo + vehiculo_MIO
    todos = {i["sujeto_id"] for i in _get(cliente_api, t, "responsable_legajos", "sujetos", limit=100).json()["items"]}
    assert {yo, otra, "vehiculo_MIO", "vehiculo_AJENO"} <= todos
    sup = {i["sujeto_id"] for i in _get(cliente_api, t, "supervisor", "sujetos", limit=100).json()["items"]}
    assert sup == {yo, "vehiculo_MIO"}
    docs_sup = {i["sujeto_id"] for i in _get(cliente_api, t, "supervisor", "documentos", limit=100).json()["items"]}
    assert docs_sup == {yo, "vehiculo_MIO"}
    docs_tec = _get(cliente_api, t, "tecnico", "documentos", sujeto_id=otra).json()
    assert docs_tec["total"] == 0                                                   # el filtro no abre el alcance
    cus = _get(cliente_api, t, "tecnico", "custodias", solo_vigentes=True).json()
    assert cus["total"] == 1 and cus["items"][0]["recurso_id"] == "vehiculo_MIO" and cus["items"][0]["custodio_id"] == yo


def test_busqueda_y_filtros(cliente_api, mundo):
    t = mundo["t"]
    r = _get(cliente_api, t, "responsable_legajos", "sujetos", q="AJENO").json()
    assert [i["sujeto_id"] for i in r["items"]] == ["vehiculo_AJENO"]
    r = _get(cliente_api, t, "responsable_legajos", "sujetos", tipo_sujeto="vehiculo").json()
    assert {i["sujeto_id"] for i in r["items"]} == {"vehiculo_MIO", "vehiculo_AJENO"}
    r = _get(cliente_api, t, "configuracion", "definiciones_requisito", q="vtv").json()
    assert r["total"] == 1 and r["items"][0]["tipo_sujeto_aplicable"] == "vehiculo"
    r = _get(cliente_api, t, "configuracion", "definiciones_requisito", categoria="competencia").json()
    assert r["total"] == 0
    resp = _get(cliente_api, t, "responsable_legajos", "usuarios", rol="supervisor")
    r = resp.json()
    assert r["total"] == 1 and r["items"][0]["usuario_id"] == t.usuarios["supervisor"] and "password" not in resp.text.lower()
    r = _get(cliente_api, t, "responsable_legajos", "usuarios", q="tecnico").json()
    assert r["total"] == 1 and r["items"][0]["sujeto_id"] == mundo["yo"]
    # baja de un sujeto: desaparece de activos, aparece con activos=false
    assert _post(cliente_api, t, "responsable_legajos", "baja_de_sujeto", {"sujeto_id": "vehiculo_AJENO"}).status_code == 200
    assert "vehiculo_AJENO" not in {i["sujeto_id"] for i in _get(cliente_api, t, "responsable_legajos", "sujetos", limit=100).json()["items"]}
    assert _get(cliente_api, t, "responsable_legajos", "sujetos", activos=False).json()["items"][0]["sujeto_id"] == "vehiculo_AJENO"
    # paginación: offset
    todo = _get(cliente_api, t, "responsable_legajos", "sujetos", limit=100).json()
    pag = _get(cliente_api, t, "responsable_legajos", "sujetos", limit=1, offset=1).json()
    assert pag["total"] == todo["total"] and pag["items"] == todo["items"][1:2]


def test_listas_dan_los_ids_que_piden_los_comandos(cliente_api, mundo):
    """Recorrido: cada id que un comando exige sale de una consulta."""
    t, yo = mundo["t"], mundo["yo"]
    # excepción → excepciones; constancia → constancias; lote → lotes; matriz → matrices; asignación → asignaciones_supervisor
    lote = str(uuid.uuid4())
    _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", {"lote_id": lote, "filas": [
        {"sujeto_id": yo, "requisito_definicion_id": mundo["req_p"], "vigente_desde": "2026-01-01", "vigente_hasta": "2027-12-31"}]}))
    lotes = _get(cliente_api, t, "responsable_legajos", "lotes", estado="aplicado").json()
    assert lote in {i["lote_id"] for i in lotes["items"]}
    assert _post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": lotes["items"][0]["lote_id"]}).status_code == 200
    mat = _post(cliente_api, t, "configuracion", "publicar_version_de_matriz", {
        "cliente_id": str(uuid.uuid4()), "locacion_id": str(uuid.uuid4()), "tipo_servicio_id": str(uuid.uuid4()), "vigente_desde": "2026-01-01",
        "lineas": [{"requisito_definicion_id": mundo["req_p"], "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True}]})
    assert mat.status_code == 200
    m = _get(cliente_api, t, "supervisor", "matrices", solo_vigentes=True).json()
    assert m["total"] == 1 and m["items"][0]["lineas"] == 1 and m["items"][0]["matriz_version_id"] == mat.json()["matriz_version_id"]
    asig = _get(cliente_api, t, "responsable_legajos", "asignaciones_supervisor", supervisor_usuario_id=t.usuarios["supervisor"]).json()
    assert asig["total"] == 1 and asig["items"][0]["sujeto_id"] == yo and asig["items"][0]["supervisor_email"].startswith("supervisor@")
    docs = _get(cliente_api, t, "responsable_legajos", "documentos", sujeto_id=yo, estado_version="todas").json()
    assert docs["total"] == 2 and {d["estado_version"] for d in docs["items"]} == {"vigente", "revertida_por_lote"} and {"documento_id", "requisito", "estado_version", "archivo_estado"} <= set(docs["items"][0])
    cus = _get(cliente_api, t, "supervisor", "custodias", recurso_id="vehiculo_MIO").json()
    assert cus["items"][0]["periodo_id"] == mundo["periodo"]
    assert _post(cliente_api, t, "supervisor", "corregir_custodia", {"periodo_id": cus["items"][0]["periodo_id"], "desde": "2025-12-31"}).status_code == 200


def test_otro_tenant_no_ve_nada(cliente_api, mundo, dos_tenants):
    ta, tb = dos_tenants
    for ruta in ("sujetos", "documentos", "custodias", "definiciones_requisito", "matrices", "lotes", "excepciones", "constancias", "asignaciones_supervisor"):
        r = _get(cliente_api, tb, "responsable_legajos", ruta)
        assert r.status_code == 200 and r.json()["total"] == 0, ruta
    usuarios_b = {i["usuario_id"] for i in _get(cliente_api, tb, "responsable_legajos", "usuarios").json()["items"]}
    assert usuarios_b == set(tb.usuarios.values()) and not usuarios_b & set(mundo["t"].usuarios.values())
