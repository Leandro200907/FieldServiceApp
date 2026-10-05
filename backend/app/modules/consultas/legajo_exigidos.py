"""Fusiona evidencia cargada con requisitos exigidos por el backlog (E-91)."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.auth.identidad import Identidad
from app.modules.consultas.presentacion_evidencia import EXPLICACION_ESTADO, _cargar_plazo_tenant
from app.modules.consultas.requisitos_exigidos_legajo import (
    AgregadoRequisitoExigido,
    agregar_requisitos_exigidos,
    resumen_exigidos_backlog,
)


def _gestion_por_categoria(categoria: str | None) -> tuple[str | None, str | None]:
    if categoria == "documento":
        return "incorporar", None
    if categoria == "induccion":
        return "solo_responsable", "registrar_induccion"
    if categoria == "competencia":
        return "solo_responsable", "registrar_acreditacion"
    return "solo_responsable", None


def _fila_sintetica_faltante(
    ag: AgregadoRequisitoExigido,
    sujeto_id: str,
    legajo: dict[str, Any],
    hoy: date,
) -> dict[str, Any]:
    gestion_tec, gestion_resp = _gestion_por_categoria(ag.categoria)
    return {
        "tipo": ag.tipo,
        "id": f"exigido-{ag.requisito_definicion_id}",
        "sujeto_id": sujeto_id,
        "tipo_sujeto": legajo.get("tipo_sujeto"),
        "identificador_natural": legajo.get("identificador_natural"),
        "nombre_apellido": legajo.get("nombre_apellido"),
        "requisito_definicion_id": ag.requisito_definicion_id,
        "requisito": ag.nombre,
        "categoria": ag.categoria,
        "locacion_id": ag.locacion_id,
        "vigente_desde": hoy.isoformat(),
        "vigente_hasta": hoy.isoformat(),
        "estado_confirmacion": "declarado",
        "origen_propuesta": False,
        "vigente_hoy": False,
        "dias_para_vencer": None,
        "vencido": False,
        "archivo_validacion": "sin_archivo",
        "estado_presentacion": "sin_documento",
        "estado_presentacion_explicacion": EXPLICACION_ESTADO["sin_documento"],
        "faltante_exigido": True,
        "exigido_backlog": True,
        "no_exigido_backlog": False,
        "gestion_tecnico": gestion_tec,
        "gestion_responsable": gestion_resp,
        "ocs_afectadas": ag.ocs_afectadas,
        "evaluacion_backlog_estado": ag.estado_peor,
    }


def _aplicar_agregado_a_fila(item: dict[str, Any], ag: AgregadoRequisitoExigido) -> None:
    item["exigido_backlog"] = True
    item["no_exigido_backlog"] = False
    item["faltante_exigido"] = False
    item["evaluacion_backlog_estado"] = ag.estado_peor
    item["ocs_afectadas"] = ag.ocs_afectadas
    if ag.es_rechazo_operadora and ag.sin_cobertura:
        nombre = ag.operadora_nombre or "la operadora"
        item["observacion_operadora"] = f"Rechazado por {nombre}"
    gestion_tec, gestion_resp = _gestion_por_categoria(ag.categoria or item.get("categoria"))
    if ag.sin_cobertura and _gestion_es_faltante_doc(ag, item):
        item["gestion_tecnico"] = gestion_tec
        item["gestion_responsable"] = gestion_resp
    if ag.estado_peor == "faltante" and not ag.evidencia_id:
        item["estado_presentacion"] = "sin_documento"
        item["faltante_exigido"] = True


def _gestion_es_faltante_doc(ag: AgregadoRequisitoExigido, item: dict[str, Any]) -> bool:
    if ag.categoria == "documento" and ag.estado_peor == "faltante" and not item.get("id", "").startswith("exigido-"):
        return True
    if item.get("faltante_exigido"):
        return True
    return ag.categoria in ("induccion", "competencia") and ag.sin_cobertura and ag.estado_peor == "faltante"


def fusionar_legajo_con_exigidos(
    session: Session,
    identidad: Identidad,
    sujeto_id: str,
    legajo: dict[str, Any],
    items: list[dict[str, Any]],
    hoy: date,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    plazo = _cargar_plazo_tenant(session, identidad.tenant_id)
    mapa = agregar_requisitos_exigidos(session, identidad, sujeto_id)
    por_rid = {str(i.get("requisito_definicion_id")): i for i in items if i.get("requisito_definicion_id")}
    salida: list[dict[str, Any]] = []
    vistos: set[str] = set()

    for rid, ag in mapa.items():
        vistos.add(rid)
        if rid in por_rid:
            fila = dict(por_rid[rid])
            _aplicar_agregado_a_fila(fila, ag)
            salida.append(fila)
        else:
            salida.append(_fila_sintetica_faltante(ag, sujeto_id, legajo, hoy))

    for rid, fila in por_rid.items():
        if rid in vistos:
            continue
        extra = dict(fila)
        extra["exigido_backlog"] = False
        extra["no_exigido_backlog"] = True
        extra["faltante_exigido"] = False
        extra["ocs_afectadas"] = []
        salida.append(extra)

    resumen_ex = resumen_exigidos_backlog(mapa, hoy, plazo)
    ocs: set[str] = set()
    for ag in mapa.values():
        if ag.sin_cobertura:
            for oc in ag.ocs_afectadas:
                clave = str(oc.get("oc_id") or oc.get("clave_origen") or "")
                if clave:
                    ocs.add(clave)
    resumen_ex["ocs_afectadas"] = len(ocs)
    return salida, resumen_ex

