"""Bandeja de revisión unificada (D3): propuestas del técnico + archivos pendientes de validación."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, envolver
from app.comun.reloj import hoy_del_tenant
from app.modules.consultas.ocs_afectadas import adjuntar_ocs_afectadas_evidencias
from app.modules.consultas.presentacion_evidencia import EXPLICACION_ESTADO, enriquecer_fila_evidencia, _cargar_plazo_tenant
from app.modules.evidencia import servicio as evidencia_svc

PestanaBandeja = Literal["todos", "propuestas", "archivos"]


def _serializar_fecha(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def _cargar_cargado_por(
    session: Session,
    tenant_id: str,
    documento_ids: list[str],
) -> dict[str, dict[str, str | None]]:
    if not documento_ids:
        return {}
    filas = session.execute(
        text(
            """
            SELECT DISTINCT ON (e.payload->>'documento_id')
                   e.payload->>'documento_id' AS documento_id,
                   e.payload->>'usuario_id' AS usuario_id,
                   e.ocurrido_en
            FROM modulo1.event_log e
            WHERE e.tenant_id = :t AND e.tipo = 'DocumentoCargado'
              AND e.payload->>'documento_id' = ANY(CAST(:ids AS text[]))
            ORDER BY e.payload->>'documento_id', e.ocurrido_en DESC
            """
        ),
        {"t": tenant_id, "ids": documento_ids},
    ).mappings().all()
    usuarios = {str(f["usuario_id"]) for f in filas if f.get("usuario_id")}
    nombres: dict[str, str] = {}
    if usuarios:
        for row in session.execute(
            text(
                "SELECT usuario_id::text, nombre, email FROM modulo1.usuario "
                "WHERE tenant_id = :t AND usuario_id::text = ANY(CAST(:uids AS text[]))"
            ),
            {"t": tenant_id, "uids": list(usuarios)},
        ).mappings():
            nombres[str(row["usuario_id"])] = row["nombre"] or row["email"]
    salida: dict[str, dict[str, str | None]] = {}
    for f in filas:
        doc_id = str(f["documento_id"])
        uid = str(f["usuario_id"]) if f.get("usuario_id") else None
        salida[doc_id] = {
            "usuario_id": uid,
            "nombre": nombres.get(uid or "", None) if uid else None,
            "cargado_en": _serializar_fecha(f.get("ocurrido_en")),
        }
    return salida


def _items_propuestas(session: Session, identidad: Identidad, hoy: date, plazo_tenant: int) -> list[dict[str, Any]]:
    filas = session.execute(
        text(
            """
            SELECT d.documento_id, d.sujeto_id, l.tipo_sujeto, l.identificador_natural, l.nombre_apellido,
                   d.requisito_definicion_id, r.nombre AS requisito, d.numero,
                   d.vigente_desde, d.vigente_hasta, d.estado_confirmacion, d.origen, d.confianza_extraccion,
                   d.creado_en, d.origen_propuesta, d.estado_version, d.archivo_estado, d.archivo_validacion,
                   d.clave_storage, r.plazo_aviso_dias, d.sucede_a,
                   v.vigente_desde AS vigente_desde_actual, v.vigente_hasta AS vigente_hasta_actual,
                   v.numero AS numero_vigente, v.creado_en AS vigente_creado_en
            FROM modulo1.documento d
            LEFT JOIN modulo1.definicion_requisito r
              ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
            LEFT JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id
            LEFT JOIN modulo1.documento v ON v.tenant_id = d.tenant_id AND v.documento_id = d.sucede_a
            WHERE d.tenant_id = :t AND d.estado_version = 'propuesta' AND d.estado_confirmacion = 'declarado'
            ORDER BY d.creado_en, d.documento_id
            """
        ),
        {"t": identidad.tenant_id},
    ).mappings().all()
    doc_ids = [str(f["documento_id"]) for f in filas]
    cargado_por = _cargar_cargado_por(session, identidad.tenant_id, doc_ids)
    items: list[dict[str, Any]] = []
    for f in filas:
        base = dict(f)
        doc_id = str(f["documento_id"])
        sujeto_id = f["sujeto_id"]
        fila_pres = {**base, "origen_propuesta": True}
        enriquecida = enriquecer_fila_evidencia(fila_pres, hoy, plazo_tenant)
        item: dict[str, Any] = {
            "tipo_item": "propuesta",
            "documento_id": doc_id,
            "sujeto_id": sujeto_id,
            "identificador_natural": f.get("identificador_natural"),
            "nombre_apellido": f.get("nombre_apellido"),
            "tipo_sujeto": f.get("tipo_sujeto"),
            "requisito_definicion_id": str(f["requisito_definicion_id"]) if f.get("requisito_definicion_id") else None,
            "requisito": f.get("requisito"),
            "numero": f.get("numero"),
            "vigente_desde": _serializar_fecha(f.get("vigente_desde")),
            "vigente_hasta": _serializar_fecha(f.get("vigente_hasta")),
            "creado_en": _serializar_fecha(f.get("creado_en")),
            "origen": f.get("origen"),
            "archivo_validacion": enriquecida.get("archivo_validacion"),
            "estado_presentacion": "propuesta_en_revision",
            "estado_presentacion_explicacion": EXPLICACION_ESTADO["propuesta_en_revision"],
            "propuesta": {
                "vigente_desde": _serializar_fecha(f.get("vigente_desde")),
                "vigente_hasta": _serializar_fecha(f.get("vigente_hasta")),
                "cargado_por": cargado_por.get(doc_id),
            },
            "vigente_comparacion": None,
            "orden_en": _serializar_fecha(f.get("creado_en")),
        }
        if f.get("sucede_a"):
            vig_cargado = _cargar_cargado_por(session, identidad.tenant_id, [str(f["sucede_a"])])
            item["vigente_comparacion"] = {
                "documento_id": str(f["sucede_a"]),
                "vigente_desde": _serializar_fecha(f.get("vigente_desde_actual")),
                "vigente_hasta": _serializar_fecha(f.get("vigente_hasta_actual")),
                "numero": f.get("numero_vigente"),
                "cargado_por": vig_cargado.get(str(f["sucede_a"])),
            }
        items.append(item)
    por_sujeto: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        por_sujeto.setdefault(it["sujeto_id"], []).append(it)
    for sid, grupo in por_sujeto.items():
        adjuntar_ocs_afectadas_evidencias(session, identidad, sid, grupo)
    return items


def _items_archivos(session: Session, identidad: Identidad, hoy: date, plazo_tenant: int) -> list[dict[str, Any]]:
    bandeja = evidencia_svc.bandeja(session, identidad, Pagina(offset=0, limit=10_000), "accion_requerida")
    raw_items = bandeja["items"]
    if not raw_items:
        return []
    doc_ids = [str(i["documento_id"]) for i in raw_items]
    filas = session.execute(
        text(
            """
            SELECT d.documento_id, d.sujeto_id, l.tipo_sujeto, l.identificador_natural, l.nombre_apellido,
                   d.requisito_definicion_id, r.nombre AS requisito, d.numero,
                   d.vigente_desde, d.vigente_hasta, d.estado_confirmacion, d.origen,
                   d.creado_en, d.estado_version, d.archivo_estado, d.archivo_validacion,
                   d.clave_storage, r.plazo_aviso_dias, d.archivo_validacion_motivo
            FROM modulo1.documento d
            LEFT JOIN modulo1.definicion_requisito r
              ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
            LEFT JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id
            WHERE d.tenant_id = :t AND d.documento_id = ANY(CAST(:ids AS uuid[]))
            """
        ),
        {"t": identidad.tenant_id, "ids": doc_ids},
    ).mappings().all()
    por_id = {str(f["documento_id"]): dict(f) for f in filas}
    cargado_por = _cargar_cargado_por(session, identidad.tenant_id, doc_ids)
    items: list[dict[str, Any]] = []
    for rid in doc_ids:
        f = por_id.get(rid)
        if f is None:
            continue
        if f.get("archivo_validacion") == "invalido":
            continue
        enriquecida = enriquecer_fila_evidencia(dict(f), hoy, plazo_tenant)
        pres = enriquecida.get("estado_presentacion") or "archivo_en_revision"
        items.append({
            "tipo_item": "archivo",
            "documento_id": rid,
            "sujeto_id": f["sujeto_id"],
            "identificador_natural": f.get("identificador_natural"),
            "nombre_apellido": f.get("nombre_apellido"),
            "tipo_sujeto": f.get("tipo_sujeto"),
            "requisito_definicion_id": str(f["requisito_definicion_id"]) if f.get("requisito_definicion_id") else None,
            "requisito": f.get("requisito"),
            "numero": f.get("numero"),
            "vigente_desde": _serializar_fecha(f.get("vigente_desde")),
            "vigente_hasta": _serializar_fecha(f.get("vigente_hasta")),
            "creado_en": _serializar_fecha(f.get("creado_en")),
            "origen": f.get("origen"),
            "archivo_validacion": enriquecida.get("archivo_validacion"),
            "archivo_validacion_motivo": f.get("archivo_validacion_motivo"),
            "estado_presentacion": pres,
            "estado_presentacion_explicacion": EXPLICACION_ESTADO.get(pres, EXPLICACION_ESTADO["archivo_en_revision"]),
            "propuesta": None,
            "vigente_comparacion": None,
            "orden_en": _serializar_fecha(f.get("creado_en")),
            "cargado_por": cargado_por.get(rid),
        })
    por_sujeto: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        por_sujeto.setdefault(it["sujeto_id"], []).append(it)
    for sid, grupo in por_sujeto.items():
        adjuntar_ocs_afectadas_evidencias(session, identidad, sid, grupo)
    items.sort(key=lambda i: (i.get("orden_en") or "", i["documento_id"]))
    return items


def bandeja_revision(
    session: Session,
    identidad: Identidad,
    p: Pagina,
    pestana: PestanaBandeja = "todos",
) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    plazo_tenant = _cargar_plazo_tenant(session, identidad.tenant_id)
    propuestas = _items_propuestas(session, identidad, hoy, plazo_tenant)
    archivos = _items_archivos(session, identidad, hoy, plazo_tenant)
    if pestana == "propuestas":
        items = propuestas
    elif pestana == "archivos":
        items = archivos
    else:
        vistos: set[str] = set()
        items = []
        for it in sorted(propuestas + archivos, key=lambda x: (x.get("orden_en") or "", x["documento_id"])):
            if it["documento_id"] in vistos:
                continue
            vistos.add(it["documento_id"])
            items.append(it)
    total = len(items)
    paginados = items[p.offset : p.offset + p.limit]
    salida = envolver(paginados, total, p)
    salida["pestana"] = pestana
    salida["conteos"] = {"todos": len({i["documento_id"] for i in propuestas + archivos}), "propuestas": len(propuestas), "archivos": len(archivos)}
    salida["hoy"] = hoy.isoformat()
    return salida
