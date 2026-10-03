from __future__ import annotations

import pytest
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

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


def _xlsx(filas: list[list[object]]) -> bytes:
    """XLSX mínimo con strings inline, sin depender de una librería externa en tests."""
    def celda(col: int, fila: int, valor: object) -> str:
        letras = ""
        n = col
        while n:
            n, resto = divmod(n - 1, 26)
            letras = chr(65 + resto) + letras
        return f'<c r="{letras}{fila}" t="inlineStr"><is><t>{escape(str(valor))}</t></is></c>'

    xml_filas = []
    for numero, valores in enumerate(filas, start=5):
        xml_filas.append(f'<row r="{numero}">' + "".join(celda(i, numero, v) for i, v in enumerate(valores, 1)) + "</row>")
    contenido = BytesIO()
    with ZipFile(contenido, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""")
        z.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Presentaciones" sheetId="1" r:id="rId1"/></sheets></workbook>""")
        z.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""")
        z.writestr("xl/worksheets/sheet1.xml", """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>""" + "".join(xml_filas) + "</sheetData></worksheet>")
    return contenido.getvalue()


_ENCABEZADOS = [
    "Operadora", "Tipo de sujeto", "Identificador del sujeto", "Sujeto ID",
    "Tipo de documento", "Requisito ID", "Documento ID", "Fecha de emisión", "Fecha de vencimiento",
    "Estado", "Fecha de exportación", "Fecha de presentación", "Fecha de respuesta", "Observación",
]


def _alta_operadora(cliente_api, tenant, nombre: str) -> None:
    r = cliente_api.post(
        "/v1/comandos/alta_operadora_oc",
        json={"nombre": nombre},
        headers=tenant.headers("configuracion"),
    )
    assert r.status_code == 200, r.text


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


def test_importa_planilla_por_filas_y_conserva_trazabilidad(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Operadora Norte")
    _alta_operadora(cliente_api, t, "Operadora Sur")
    req = _alta_def(cliente_api, t, "Apto médico")
    sujeto = _alta_persona(cliente_api, t, "persona_e2e_vencido")
    doc = _cargar(cliente_api, t, sujeto, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Operadora Norte", "persona", "persona_e2e_vencido", sujeto, "Apto médico", req, "",
         "2026-09-27", "2027-09-25", "aceptado", "2026-09-27T10:00:00+00:00",
         "2026-09-27T11:00:00+00:00", "2026-09-28T09:00:00+00:00", "Aceptado por portal"],
        ["Operadora Sur", "persona", "persona_e2e_vencido", sujeto, "Apto médico", req, "",
         "2026-09-27", "2027-09-25", "aceptado", "2026-09-27T10:00:00+00:00",
         "", "", "Faltan fechas"],
    ]
    headers = {**t.headers("responsable_legajos", "importacion-planilla-1"),
               "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
               "X-Nombre-Archivo": "presentaciones_septiembre.xlsx"}
    respuesta = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert (cuerpo["filas_totales"], cuerpo["filas_aceptadas"], cuerpo["filas_rechazadas"]) == (2, 1, 1)
    assert cuerpo["resultados"][0]["documento_id"] == doc["documento_id"]
    assert cuerpo["errores"][0]["fila"] == 7
    with tenant_session(t.tenant_id) as session:
        entrega = session.execute(text("""
            SELECT e.estado, e.fuente_archivo, e.fuente_hoja, e.fuente_fila
            FROM modulo1.entrega_documento_operadora e WHERE e.documento_id = :d
        """), {"d": doc["documento_id"]}).mappings().one()
        assert dict(entrega) == {"estado": "aceptado", "fuente_archivo": "presentaciones_septiembre.xlsx",
                                "fuente_hoja": "Presentaciones", "fuente_fila": 6}


def test_importador_no_puede_resolver_documentos_de_otro_tenant(cliente_api, dos_tenants):
    propio, ajeno = dos_tenants
    _alta_operadora(cliente_api, propio, "Operadora Norte")
    req_ajeno = _alta_def(cliente_api, ajeno, "Apto médico")
    sujeto_ajeno = _alta_persona(cliente_api, ajeno, "persona_externa")
    doc_ajeno = _cargar(cliente_api, ajeno, sujeto_ajeno, req_ajeno, desde="2026-09-27", hasta="2027-09-25")
    filas = [_ENCABEZADOS, [
        "Operadora Norte", "persona", "persona_externa", sujeto_ajeno, "Apto médico", req_ajeno, "",
        "2026-09-27", "2027-09-25", "enviado", "", "2026-09-27T11:00:00+00:00", "", "",
    ]]
    headers = {**propio.headers("responsable_legajos"),
               "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    respuesta = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["filas_aceptadas"] == 0
    assert respuesta.json()["filas_rechazadas"] == 1
    with tenant_session(propio.tenant_id) as session:
        assert session.execute(text("SELECT count(*) FROM modulo1.entrega_documento_operadora")).scalar_one() == 0
    with tenant_session(ajeno.tenant_id) as session:
        assert session.execute(text(
            "SELECT count(*) FROM modulo1.entrega_documento_operadora WHERE documento_id = :d"
        ), {"d": doc_ajeno["documento_id"]}).scalar_one() == 0


def test_importar_planilla_operadoras_exige_responsable_legajos(cliente_api, tenant_de_prueba, monkeypatch):
    t = tenant_de_prueba
    invocaciones: list[int] = []

    def _no_debe_parsear(*_args, **_kwargs):
        invocaciones.append(1)
        raise AssertionError("leer_planilla no debe ejecutarse sin rol responsable_legajos")

    monkeypatch.setattr("app.modules.operadoras.router.leer_planilla", _no_debe_parsear)
    headers = {
        **t.headers("tecnico"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    respuesta = cliente_api.post(
        "/v1/comandos/importar_planilla_operadoras",
        content=_xlsx([_ENCABEZADOS, ["Operadora Norte", "persona", "x", "y", "Apto", "z", "", "", "enviado", "", "", "", ""]]),
        headers=headers,
    )
    assert respuesta.status_code == 403
    assert invocaciones == []


def test_importar_planilla_operadoras_idempotente_por_clave(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Operadora Norte")
    req = _alta_def(cliente_api, t, "Apto idem")
    sujeto = _alta_persona(cliente_api, t, "persona_idem")
    doc = _cargar(cliente_api, t, sujeto, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Operadora Norte", "persona", "persona_idem", sujeto, "Apto idem", req, "",
         "2026-09-27", "2027-09-25", "enviado", "", "2026-09-27T11:00:00+00:00", "", ""],
    ]
    xlsx = _xlsx(filas)
    base = {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "X-Nombre-Archivo": "idem.xlsx",
    }
    h1 = {**t.headers("responsable_legajos", "planilla-idem-1"), **base}
    h2 = {**t.headers("responsable_legajos", "planilla-idem-2"), **base}
    r1 = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=xlsx, headers=h1)
    r2 = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=xlsx, headers=h2)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert r2.json()["filas_aceptadas"] == 1
    assert r2.json()["resultados"][0]["documento_id"] == doc["documento_id"]



