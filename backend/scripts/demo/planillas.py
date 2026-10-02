"""Generación e importación de planillas XLSX bajo scripts/demo_planillas/<slug>/."""
from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path

from openpyxl import load_workbook

from app.db import tenant_session
from app.modules.legajos.infra import ejecutar_comando
from app.modules.oc.lector_planilla_oc import leer_planilla_oc
from app.modules.operadoras.lector_xlsx import leer_planilla as leer_planilla_operadoras
from app.modules.operadoras import servicio as op_svc
from app.modules.oc import servicio as oc_svc
from app.auth.identidad import Rol
from scripts.demo.config import dni_tecnico
from scripts.demo.contexto import EstadoTenant
from scripts.demo.db_util import ErrorDemo
from scripts.demo.fechas import hoy_tenant

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLA = RAIZ.parents[1] / "frontend" / "public" / "Plantilla_presentaciones_operadoras.xlsx"
ENCABEZADOS_OC = [
    "Clave OC", "Referencia", "Operadora", "Locación", "Tipo de servicio",
    "Vigencia desde", "Vigencia hasta", "Estado",
]


def _dir_slug(est: EstadoTenant) -> Path:
    d = RAIZ / "demo_planillas" / est.spec.slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _guardar_oc(est: EstadoTenant, path: Path, filas_datos: list[list]) -> None:
    from html import escape
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    def celda(col: int, fila: int, valor: object) -> str:
        letras = ""
        n = col
        while n:
            n, resto = divmod(n - 1, 26)
            letras = chr(65 + resto) + letras
        return f'<c r="{letras}{fila}" t="inlineStr"><is><t>{escape(str(valor))}</t></is></c>'

    xml_filas = []
    for numero, valores in enumerate([ENCABEZADOS_OC] + filas_datos, start=1):
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
<sheets><sheet name="OC" sheetId="1" r:id="rId1"/></sheets></workbook>""")
        z.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""")
        z.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + "".join(xml_filas)
            + "</sheetData></worksheet>",
        )
    path.write_bytes(contenido.getvalue())


def generar_planillas(est: EstadoTenant) -> Path:
    out = _dir_slug(est)
    hoy = hoy_tenant(est.tenant_id)
    docs = []
    for op in ("YPF", "Vista", "Tecpetrol"):
        doc_id = est.documentos.get(f"t1_vigente_Apto médico") or next(iter(est.documentos.values()), "")
        docs.append((op, doc_id))
    wb = load_workbook(PLANTILLA)
    hoja = wb["Presentaciones"]

    def fila_presentacion(op: str, doc_id: str, estado: str, obs: str = "") -> None:
        nonlocal row
        hoja.cell(row=row, column=1, value=op)
        hoja.cell(row=row, column=2, value="persona")
        hoja.cell(row=row, column=3, value=est.sujetos["tecnico1"])
        hoja.cell(row=row, column=4, value=dni_tecnico(est.spec.slug, 1))
        hoja.cell(row=row, column=5, value="Apto médico")
        hoja.cell(row=row, column=6, value=est.requisitos["Apto médico"])
        hoja.cell(row=row, column=7, value=doc_id)
        hoja.cell(row=row, column=10, value=estado)
        hoja.cell(row=row, column=14, value=obs)
        row += 1

    row = 6
    estados = ["exportado", "enviado", "aceptado", "rechazado", "pendiente"]
    for i, (op, doc) in enumerate(docs):
        fila_presentacion(op, doc, estados[i], "Observación demo" if estados[i] == "rechazado" else "")
    for op, doc in docs[:2]:
        fila_presentacion(op, doc, "reenviado")
        fila_presentacion(op, doc, "aceptado")
    p1 = out / "presentaciones_1.xlsx"
    wb.save(p1)
    wb2 = load_workbook(p1)
    wb2.save(out / "presentaciones_2.xlsx")

    wb_err = load_workbook(PLANTILLA)
    h = wb_err["Presentaciones"]
    h.cell(row=6, column=1, value="YPF SA")
    h.cell(row=7, column=7, value="00000000-0000-0000-0000-000000000099")
    h.cell(row=8, column=9, value="2099-99-99")
    h.cell(row=9, column=1, value="")
    wb_err.save(out / "presentaciones_con_errores.xlsx")

    oc_rows = [
        [
            f"OC-PLAN-{est.spec.slug}-OK",
            "ref",
            "YPF",
            "YPF — Locación 1",
            "Wireline",
            (hoy + timedelta(days=60)).isoformat(),
            (hoy + timedelta(days=90)).isoformat(),
            "activo",
        ],
        [
            f"OC-PLAN-{est.spec.slug}-BAD",
            "ref",
            "Operadora Inexistente",
            "YPF — Locación 1",
            "Wireline",
            hoy.isoformat(),
            (hoy + timedelta(days=10)).isoformat(),
            "activo",
        ],
    ]
    _guardar_oc(est, out / "oc.xlsx", oc_rows)
    return out


def _exigir_filas_importadas(etiqueta: str, resp: dict) -> None:
    if int(resp.get("filas_aceptadas") or 0) == 0:
        rech = resp.get("filas_rechazadas")
        raise ErrorDemo(f"{etiqueta}: importación sin filas aceptadas (rechazadas={rech})")


def importar_planillas(est: EstadoTenant, idn) -> None:
    base = _dir_slug(est)
    for nombre in ("presentaciones_1.xlsx", "presentaciones_2.xlsx"):
        data = (base / nombre).read_bytes()
        filas, err = leer_planilla_operadoras(data)
        resp = ejecutar_comando(
            idn,
            str(uuid.uuid4()),
            (Rol.RESPONSABLE_LEGAJOS,),
            lambda s: op_svc.importar_filas(
                s, idn, archivo=nombre, hoja="Presentaciones", filas=filas, errores_lectura=err
            ),
            ruta="/comandos/importar_planilla_operadoras",
            body={"archivo": nombre},
        )
        _exigir_filas_importadas(f"planilla operadoras {nombre} ({est.spec.slug})", resp)
    lote = uuid.uuid5(uuid.NAMESPACE_DNS, f"import-oc-{est.spec.slug}")
    data_oc = (base / "oc.xlsx").read_bytes()
    filas, err = leer_planilla_oc(data_oc)
    with tenant_session(est.tenant_id) as s:
        from app.comun.idempotencia import ejecutar_idempotente, fingerprint_de

        resp = ejecutar_idempotente(
            est.tenant_id,
            idn.usuario_id,
            f"lote_oc:{lote}",
            fingerprint_de("POST", "/comandos/importar_planilla_oc", {"lote_id": str(lote)}),
            lambda s: oc_svc.importar_lote_oc(s, idn, str(lote), "planilla", filas),
        )
        _exigir_filas_importadas(f"planilla OC ({est.spec.slug})", resp)
