"""Certificado propio (E-97): shell de archivo para inducción/competencia."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado
from app.comun.reloj import hoy_del_tenant
from app.config import settings

ORIGEN_CERTIFICADO_RESPALDO = "certificado_respaldo"


def promover_padres_si_certificado_valido(session: Session, tenant_id: str, soporte_documento_id: str) -> None:
    """Tras validar el archivo del certificado, verifica registros padre declarados."""
    padres = session.execute(
        text(
            """
            SELECT d.documento_id::text
            FROM modulo1.documento_soporte ds
            JOIN modulo1.documento d
              ON d.tenant_id = ds.tenant_id AND d.documento_id = ds.documento_id
            WHERE ds.tenant_id = :t
              AND ds.soporte_documento_id = CAST(:s AS uuid)
              AND ds.es_certificado_propio
              AND d.estado_confirmacion = 'declarado'
            """
        ),
        {"t": tenant_id, "s": soporte_documento_id},
    ).scalars().all()
    for padre_id in padres:
        session.execute(
            text(
                "UPDATE modulo1.documento SET estado_confirmacion = 'verificado' "
                "WHERE tenant_id = :t AND documento_id = CAST(:d AS uuid)"
            ),
            {"t": tenant_id, "d": padre_id},
        )


def _exigir_vigencia_registro_certificado(session: Session, tenant_id: str, desde: date, hasta: date) -> None:
    from datetime import timedelta

    hoy = hoy_del_tenant(session, tenant_id)
    if desde > hoy:
        raise ErrorDeDominio(
            "La fecha de realización no puede ser futura",
            {"vigente_desde": str(desde), "hoy": str(hoy)},
            codigo="vigencia_desde_futura",
        )
    if desde > hasta:
        raise ErrorDeDominio(
            "vigente_desde no puede ser posterior a vigente_hasta",
            {"vigente_desde": str(desde), "vigente_hasta": str(hasta)},
        )
    max_anios = settings.propuesta_max_anios_vigencia
    if max_anios < 1:
        raise ErrorDeDominio("propuesta_max_anios_vigencia debe ser >= 1", {"propuesta_max_anios_vigencia": max_anios})
    tope = hoy + timedelta(days=365 * max_anios)
    if hasta > tope:
        raise ErrorDeDominio(
            f"La fecha de vencimiento no puede superar {max_anios} años desde hoy",
            {"vigente_hasta": str(hasta), "tope": str(tope), "max_anios": max_anios},
            codigo="vigencia_propuesta_excede_plazo",
        )


def insertar_shell_certificado_respaldo(session: Session, tenant_id: str, persona_id: str) -> str:
    hoy = hoy_del_tenant(session, tenant_id)
    doc_id = str(uuid.uuid4())
    session.execute(
        text(
            """
            INSERT INTO modulo1.documento (
                documento_id, tenant_id, sujeto_id, requisito_definicion_id,
                vigente_desde, vigente_hasta, estado_confirmacion, estado_version,
                origen_propuesta, version, origen, archivo_estado, archivo_validacion
            ) VALUES (
                CAST(:d AS uuid), :t, :sj, NULL, :desde, :hasta, 'declarado', 'vigente',
                false, 1, :origen, 'sin_archivo', 'pendiente'
            )
            """
        ),
        {
            "d": doc_id,
            "t": tenant_id,
            "sj": persona_id,
            "desde": hoy,
            "hasta": hoy,
            "origen": ORIGEN_CERTIFICADO_RESPALDO,
        },
    )
    return doc_id


def _estado_confirmacion_desde_certificado(archivo_validacion: str | None) -> str:
    return "verificado" if archivo_validacion == "valido" else "declarado"


def _exigir_y_preparar_certificado(
    session: Session,
    tenant_id: str,
    persona_id: str,
    certificado_documento_id: str,
    vigente_desde: date,
    vigente_hasta: date,
) -> dict[str, Any]:
    fila = session.execute(
        text(
            """
            SELECT documento_id, sujeto_id, origen, requisito_definicion_id,
                   archivo_estado, archivo_validacion
            FROM modulo1.documento
            WHERE tenant_id = :t AND documento_id = CAST(:d AS uuid)
            FOR UPDATE
            """
        ),
        {"t": tenant_id, "d": certificado_documento_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Certificado inexistente", {"certificado_documento_id": certificado_documento_id})
    if fila["origen"] != ORIGEN_CERTIFICADO_RESPALDO:
        raise ErrorDeDominio(
            "El documento no es un certificado de respaldo creado para este registro",
            {"certificado_documento_id": certificado_documento_id, "origen": fila["origen"]},
            codigo="respaldo_tipo_no_admitido",
        )
    if str(fila["sujeto_id"]) != persona_id:
        raise NoEncontrado(
            "Certificado inexistente o de otro sujeto",
            {"certificado_documento_id": certificado_documento_id},
        )
    if fila["archivo_estado"] != "confirmado":
        raise ErrorDeDominio(
            "El certificado debe tener el archivo subido y confirmado antes del registro",
            {"certificado_documento_id": certificado_documento_id, "archivo_estado": fila["archivo_estado"]},
            codigo="certificado_sin_archivo_confirmado",
        )
    ya_usado = session.execute(
        text(
            "SELECT 1 FROM modulo1.documento_soporte "
            "WHERE tenant_id = :t AND soporte_documento_id = CAST(:s AS uuid) AND es_certificado_propio LIMIT 1"
        ),
        {"t": tenant_id, "s": certificado_documento_id},
    ).first()
    if ya_usado is not None:
        raise Conflicto(
            "El certificado ya fue usado en otro registro",
            {"certificado_documento_id": certificado_documento_id},
            codigo="certificado_ya_utilizado",
        )
    _exigir_vigencia_registro_certificado(session, tenant_id, vigente_desde, vigente_hasta)
    session.execute(
        text(
            "UPDATE modulo1.documento SET vigente_desde = :desde, vigente_hasta = :hasta "
            "WHERE tenant_id = :t AND documento_id = CAST(:d AS uuid)"
        ),
        {"t": tenant_id, "d": certificado_documento_id, "desde": vigente_desde, "hasta": vigente_hasta},
    )
    return dict(fila)


def enlazar_certificado_propio(
    session: Session,
    tenant_id: str,
    documento_padre_id: str,
    certificado_documento_id: str,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO modulo1.documento_soporte (
                tenant_id, documento_id, soporte_documento_id, es_certificado_propio
            ) VALUES (:t, :padre, CAST(:soporte AS uuid), true)
            """
        ),
        {"t": tenant_id, "padre": documento_padre_id, "soporte": certificado_documento_id},
    )
