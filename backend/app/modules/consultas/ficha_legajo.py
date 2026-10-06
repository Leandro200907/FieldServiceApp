"""Presentación de filas y tarjetas en ficha de legajo (E-101 / E-104)."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.resolucion_evidencia import (
    agrupar_soportes_por_documento,
    archivo_validacion_para_evaluacion_documental,
)
from app.modules.consultas.presentacion_evidencia import (
    EXPLICACION_ESTADO,
    _cargar_plazo_tenant,
    enriquecer_fila_evidencia,
    estado_vigencia_presentacion,
)


def cargar_soportes_por_documento(session: Session, tenant_id: str, documento_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not documento_ids:
        return {}
    filas = session.execute(
        text(
            """
            SELECT ds.documento_id::text AS documento_padre_id,
                   s.documento_id::text AS soporte_documento_id,
                   s.archivo_estado, s.archivo_validacion, s.clave_storage, ds.es_certificado_propio
            FROM modulo1.documento_soporte ds
            JOIN modulo1.documento s ON s.tenant_id = ds.tenant_id AND s.documento_id = ds.soporte_documento_id
            WHERE ds.tenant_id = :t AND ds.documento_id = ANY(CAST(:ids AS uuid[]))
            """
        ),
        {"t": tenant_id, "ids": documento_ids},
    ).mappings().all()
    return agrupar_soportes_por_documento(filas)


def _certificado_respaldo_documento_id(soportes: list[dict[str, Any]] | None) -> str | None:
    if not soportes:
        return None
    for s in soportes:
        if not s.get("es_certificado_propio"):
            continue
        sid = str(s.get("soporte_documento_id") or s.get("documento_id") or "")
        if sid:
            return sid
    return None


def _archivo_efectivo_fila(fila: dict[str, Any], soportes: list[dict[str, Any]] | None) -> str:
    cat = (fila.get("categoria") or "documento").lower()
    if cat in ("competencia", "induccion"):
        return archivo_validacion_para_evaluacion_documental(
            fila,
            categoria=fila.get("categoria"),
            soportes=soportes,
        )
    from app.modules.consultas.presentacion_evidencia import _archivo_validacion_de_fila

    return _archivo_validacion_de_fila(fila)


def _bucket_calendario(hoy: date, *, vigente_hasta: date | None, vencido: bool, plazo_aviso: int) -> str:
    est = estado_vigencia_presentacion(hoy, vigente_hasta=vigente_hasta, vencido=vencido, plazo_aviso_dias=plazo_aviso)
    if est == "vencida":
        return "vencidos"
    if est == "por_vencer":
        return "por_vencer"
    return "vigentes"


def bucket_tarjeta_exigido_desde_agregado(
    *,
    evidencia_id: str | None,
    archivo_validacion: str | None,
    vigente_hasta: date | None,
    hoy: date,
    plazo_aviso: int,
    vencido_calendario: bool,
) -> str:
    """Tarjetas E-101: sin respaldo válido → Sin documento; pendiente → calendario."""
    if not evidencia_id:
        return "sin_documento"
    arch = archivo_validacion
    if arch in ("sin_archivo", "invalido"):
        return "sin_documento"
    if arch == "pendiente":
        return _bucket_calendario(hoy, vigente_hasta=vigente_hasta, vencido=vencido_calendario, plazo_aviso=plazo_aviso)
    return _bucket_calendario(hoy, vigente_hasta=vigente_hasta, vencido=vencido_calendario, plazo_aviso=plazo_aviso)


def estado_fila_y_observacion(
    item: dict[str, Any],
    *,
    hoy: date,
    plazo_aviso: int,
    archivo_efectivo: str,
) -> tuple[str, str]:
    if item.get("estado_presentacion") == "sin_documento" or item.get("faltante_exigido"):
        return "Sin documento", EXPLICACION_ESTADO["sin_documento"]
    if item.get("estado_presentacion") == "propuesta_en_revision" and item.get("propuesta_en_revision"):
        return "Propuesta en revisión", EXPLICACION_ESTADO["propuesta_en_revision"]
    if archivo_efectivo in ("sin_archivo", "invalido"):
        obs = item.get("motivo_archivo_invalido") or EXPLICACION_ESTADO.get("evidencia_invalida", "")
        if archivo_efectivo == "sin_archivo":
            cat = (item.get("categoria") or "").lower()
            if cat == "induccion":
                obs = "El respaldo no es un certificado propio válido; registrá la inducción con su certificado."
            elif cat == "competencia":
                obs = "El respaldo no es un certificado propio válido; registrá la competencia con su certificado."
            else:
                obs = EXPLICACION_ESTADO["sin_archivo_respaldo"]
        return "Sin respaldo válido", obs
    if archivo_efectivo == "pendiente":
        hasta = item.get("vigente_hasta")
        if isinstance(hasta, str):
            hasta = date.fromisoformat(hasta[:10])
        vencido = bool(item.get("vencido"))
        if hasta is not None and not vencido:
            vencido = hasta < hoy
        cal = _bucket_calendario(hoy, vigente_hasta=hasta, vencido=vencido, plazo_aviso=plazo_aviso)
        obs = EXPLICACION_ESTADO["archivo_en_revision"]
        if cal == "vencidos":
            return "Vencida", obs
        if cal == "por_vencer":
            return "Por vencer", obs
        return "Pendiente de validación", obs
    hasta = item.get("vigente_hasta")
    if isinstance(hasta, str):
        hasta = date.fromisoformat(hasta[:10])
    vencido = bool(item.get("vencido"))
    if hasta is not None and not vencido:
        vencido = hasta < hoy
    cal = _bucket_calendario(hoy, vigente_hasta=hasta, vencido=vencido, plazo_aviso=plazo_aviso)
    if cal == "vencidos":
        return "Vencida", EXPLICACION_ESTADO["vencida"]
    if cal == "por_vencer":
        return "Por vencer", EXPLICACION_ESTADO["por_vencer"]
    return "Vigente", "—"


def enriquecer_items_ficha_legajo(
    session: Session,
    tenant_id: str,
    items: list[dict[str, Any]],
    hoy: date,
) -> None:
    plazo = _cargar_plazo_tenant(session, tenant_id)
    ids = [str(i["id"]) for i in items if i.get("id") and not str(i["id"]).startswith("exigido-")]
    soportes_map = cargar_soportes_por_documento(session, tenant_id, ids)
    loc_ids = {str(i.get("locacion_id")) for i in items if i.get("locacion_id")}
    loc_nombres: dict[str, str] = {}
    if loc_ids:
        filas = session.execute(
            text(
                "SELECT locacion_id::text, nombre FROM modulo1.locacion_oc "
                "WHERE tenant_id = :t AND locacion_id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"t": tenant_id, "ids": list(loc_ids)},
        ).all()
        loc_nombres = {str(r[0]): str(r[1]) for r in filas}

    for raw in items:
        doc_id = str(raw.get("id") or "")
        soportes = soportes_map.get(doc_id, [])
        base = dict(raw)
        archivo_efectivo = _archivo_efectivo_fila(base, soportes)
        enriquecido = enriquecer_fila_evidencia(
            base,
            hoy,
            plazo,
            archivo_validacion_override=archivo_efectivo,
        )
        raw.clear()
        raw.update(enriquecido)
        lid = raw.get("locacion_id")
        if lid and str(lid) in loc_nombres:
            raw["locacion_nombre"] = loc_nombres[str(lid)]
            raw["ambito_nombre"] = loc_nombres[str(lid)]
        cert_id = _certificado_respaldo_documento_id(soportes)
        if cert_id and archivo_efectivo in ("valido", "pendiente"):
            raw["certificado_respaldo_documento_id"] = cert_id
        estado, obs = estado_fila_y_observacion(raw, hoy=hoy, plazo_aviso=plazo, archivo_efectivo=archivo_efectivo)
        raw["estado_fila"] = estado
        raw["observacion_ficha"] = obs


def ofrece_registro_respaldo_responsable(item: dict[str, Any]) -> bool:
    cat = (item.get("categoria") or "").lower()
    if cat not in ("induccion", "competencia"):
        return False
    arch = item.get("archivo_validacion")
    if arch in ("valido", "pendiente"):
        return False
    if item.get("faltante_exigido"):
        return True
    return arch in ("sin_archivo", "invalido")
