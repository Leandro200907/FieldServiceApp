"""Estados de presentación de evidencia para consultas de legajo (ronda 1-b).

Unifica documento vigente confirmado vs. propuesta pendiente, archivo_validacion y
«por vencer» según plazo de aviso del tenant/requisito.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.comun.reloj import hoy_del_tenant

ESTADOS_PRESENTACION = (
    "verificada",
    "declarada",
    "por_vencer",
    "vencida",
    "archivo_en_revision",
    "evidencia_invalida",
    "propuesta_en_revision",
)

EXPLICACION_ESTADO: dict[str, str] = {
    "verificada": "La evidencia está confirmada y vigente dentro de su período.",
    "declarada": "Hay datos cargados que aún no fueron verificados por un responsable.",
    "por_vencer": "La evidencia sigue vigente pero vence dentro del plazo de aviso configurado.",
    "vencida": "La fecha de vigencia ya pasó; hace falta renovar o reemplazar la evidencia.",
    "archivo_en_revision": "El archivo adjunto está pendiente de validación técnica.",
    "evidencia_invalida": "El archivo fue rechazado en la validación; hay que subir una evidencia nueva.",
    "propuesta_en_revision": "Un técnico propuso una renovación que espera confirmación; no reemplaza la versión vigente.",
}


def _archivo_validacion_de_fila(fila: Mapping[str, Any]) -> str:
    if fila.get("archivo_validacion") is not None:
        return str(fila["archivo_validacion"])
    archivo_estado = fila.get("archivo_estado")
    clave = fila.get("clave_storage")
    if archivo_estado == "confirmado":
        return "pendiente"
    if clave is None:
        return "sin_archivo"
    return "pendiente"


def _es_propuesta_pendiente(fila: Mapping[str, Any]) -> bool:
    return bool(fila.get("origen_propuesta")) and fila.get("estado_confirmacion") == "declarado"


def _plazo_aviso(plazo_requisito: int | None, plazo_tenant: int) -> int:
    return plazo_requisito if plazo_requisito is not None else plazo_tenant


def estado_presentacion(
    hoy: date,
    *,
    estado_confirmacion: str,
    vigente_hasta: date | None,
    vencido: bool,
    archivo_validacion: str,
    plazo_aviso_dias: int,
) -> str:
    if archivo_validacion == "invalido":
        base = "evidencia_invalida"
    elif archivo_validacion == "pendiente":
        base = "archivo_en_revision"
    elif estado_confirmacion == "declarado":
        base = "declarada"
    elif vencido:
        base = "vencida"
    elif vigente_hasta is not None and (vigente_hasta - hoy).days <= plazo_aviso_dias:
        base = "por_vencer"
    else:
        base = "verificada"
    return base


def enriquecer_fila_evidencia(
    fila: dict[str, Any],
    hoy: date,
    plazo_tenant: int,
) -> dict[str, Any]:
    archivo = _archivo_validacion_de_fila(fila)
    plazo = _plazo_aviso(fila.get("plazo_aviso_dias"), plazo_tenant)
    hasta = fila.get("vigente_hasta")
    if isinstance(hasta, str):
        hasta = date.fromisoformat(hasta)
    vencido = bool(fila.get("vencido"))
    if hasta is not None and not vencido:
        vencido = hasta < hoy
    estado = estado_presentacion(
        hoy,
        estado_confirmacion=str(fila.get("estado_confirmacion") or ""),
        vigente_hasta=hasta,
        vencido=vencido,
        archivo_validacion=archivo,
        plazo_aviso_dias=plazo,
    )
    adicionales: list[str] = []
    if archivo == "invalido" and estado != "evidencia_invalida":
        adicionales.append("evidencia_invalida")
    if archivo == "pendiente" and estado not in ("archivo_en_revision",):
        adicionales.append("archivo_en_revision")
    if vencido and estado != "vencida":
        adicionales.append("vencida")
    salida = dict(fila)
    salida["archivo_validacion"] = archivo
    salida["estado_presentacion"] = estado
    salida["estado_presentacion_explicacion"] = EXPLICACION_ESTADO[estado]
    if adicionales:
        salida["estados_adicionales"] = adicionales
        salida["estados_adicionales_explicacion"] = {e: EXPLICACION_ESTADO[e] for e in adicionales}
    return salida


def _cargar_plazo_tenant(session: Session, tenant_id: str) -> int:
    from sqlalchemy import text

    fila = session.execute(
        text("SELECT plazo_aviso_dias FROM modulo1.configuracion_alertas WHERE tenant_id = :t"),
        {"t": tenant_id},
    ).first()
    return int(fila[0]) if fila and fila[0] is not None else 30


def filas_evidencia_para_legajo(
    session: Session,
    tenant_id: str,
    sujeto_id: str,
    hoy: date | None = None,
) -> list[dict[str, Any]]:
    """Un ítem por requisito: versión confirmada vigente; propuesta aparte si existe."""
    from sqlalchemy import text

    hoy = hoy or hoy_del_tenant(session, tenant_id)
    plazo_tenant = _cargar_plazo_tenant(session, tenant_id)
    filas = session.execute(
        text(
            """
            SELECT CASE r.categoria WHEN 'competencia' THEN 'acreditacion'
                                    WHEN 'induccion' THEN 'induccion'
                                    ELSE 'documento' END AS tipo,
                   d.documento_id AS id, d.sujeto_id, d.requisito_definicion_id,
                   r.nombre AS requisito, r.categoria, d.vigente_desde, d.vigente_hasta,
                   d.estado_confirmacion, d.origen_propuesta, d.locacion_id,
                   d.estado_version, d.archivo_estado, d.archivo_validacion, d.clave_storage,
                   d.sucede_a, r.plazo_aviso_dias,
                   l.identificador_natural
            FROM modulo1.documento d
            LEFT JOIN modulo1.definicion_requisito r
              ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
            LEFT JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id
            WHERE d.tenant_id = :t AND d.sujeto_id = :s
              AND d.estado_version IN ('vigente', 'sucedida')
            ORDER BY d.requisito_definicion_id, d.estado_version DESC, d.version DESC
            """
        ),
        {"t": tenant_id, "s": sujeto_id},
    ).mappings().all()
    por_req: dict[str, list[dict[str, Any]]] = {}
    for f in filas:
        rid = str(f["requisito_definicion_id"])
        por_req.setdefault(rid, []).append(dict(f))

    salida: list[dict[str, Any]] = []
    for grupo in por_req.values():
        vigente = next((g for g in grupo if g["estado_version"] == "vigente"), None)
        if vigente is None:
            continue
        if _es_propuesta_pendiente(vigente) and vigente.get("sucede_a"):
            confirmada = next(
                (g for g in grupo if str(g["id"]) == str(vigente["sucede_a"]) and g["estado_version"] == "sucedida"),
                None,
            )
            if confirmada is None:
                confirmada = session.execute(
                    text(
                        """
                        SELECT CASE r.categoria WHEN 'competencia' THEN 'acreditacion'
                                                WHEN 'induccion' THEN 'induccion'
                                                ELSE 'documento' END AS tipo,
                               d.documento_id AS id, d.sujeto_id, d.requisito_definicion_id,
                               r.nombre AS requisito, r.categoria, d.vigente_desde, d.vigente_hasta,
                               d.estado_confirmacion, d.origen_propuesta, d.locacion_id,
                               d.estado_version, d.archivo_estado, d.archivo_validacion, d.clave_storage,
                               d.sucede_a, r.plazo_aviso_dias,
                               l.identificador_natural
                        FROM modulo1.documento d
                        LEFT JOIN modulo1.definicion_requisito r
                          ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
                        LEFT JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id
                        WHERE d.tenant_id = :t AND d.documento_id = CAST(:d AS uuid)
                        """
                    ),
                    {"t": tenant_id, "d": str(vigente["sucede_a"])},
                ).mappings().first()
                if confirmada is not None:
                    confirmada = dict(confirmada)
            if confirmada is not None:
                base = _fila_con_vigencia(confirmada, hoy)
                base = enriquecer_fila_evidencia(base, hoy, plazo_tenant)
                base["propuesta_en_revision"] = {
                    "documento_id": str(vigente["id"]),
                    "vigente_desde": vigente["vigente_desde"].isoformat() if vigente.get("vigente_desde") else None,
                    "vigente_hasta": vigente["vigente_hasta"].isoformat() if vigente.get("vigente_hasta") else None,
                    "estado_presentacion": "propuesta_en_revision",
                    "estado_presentacion_explicacion": EXPLICACION_ESTADO["propuesta_en_revision"],
                }
                salida.append(base)
                continue
        if _es_propuesta_pendiente(vigente) and not vigente.get("sucede_a"):
            base = _fila_con_vigencia(vigente, hoy)
            base = enriquecer_fila_evidencia(base, hoy, plazo_tenant)
            base["estado_presentacion"] = "propuesta_en_revision"
            base["estado_presentacion_explicacion"] = EXPLICACION_ESTADO["propuesta_en_revision"]
            salida.append(base)
            continue
        base = _fila_con_vigencia(vigente, hoy)
        salida.append(enriquecer_fila_evidencia(base, hoy, plazo_tenant))
    salida.sort(key=lambda i: (i.get("vigente_hasta") or "", i.get("tipo") or "", i.get("requisito") or ""))
    return salida


def _serializar_valor_fila(valor: Any) -> Any:
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if hasattr(valor, "isoformat") and not isinstance(valor, str):
        return valor.isoformat()
    return valor


def _fila_con_vigencia(fila: dict[str, Any], hoy: date) -> dict[str, Any]:
    desde: date = fila["vigente_desde"]
    hasta: date | None = fila["vigente_hasta"]
    salida = {k: _serializar_valor_fila(v) for k, v in fila.items()}
    salida["vigente_hoy"] = desde <= hoy and (hasta is None or hoy <= hasta)
    salida["dias_para_vencer"] = (hasta - hoy).days if hasta is not None else None
    salida["vencido"] = hasta is not None and hasta < hoy
    salida["id"] = str(salida["id"])
    if salida.get("requisito_definicion_id") is not None:
        salida["requisito_definicion_id"] = str(salida["requisito_definicion_id"])
    return salida


def resumen_desde_items(items: list[dict[str, Any]]) -> dict[str, int]:
    vigentes = por_vencer = vencidos = 0
    for i in items:
        est = i.get("estado_presentacion")
        if est == "vencida" or i.get("vencido"):
            vencidos += 1
        elif est == "por_vencer":
            por_vencer += 1
        elif est in ("verificada", "declarada", "archivo_en_revision", "evidencia_invalida"):
            if i.get("vigente_hoy"):
                vigentes += 1
    return {
        "total": len(items),
        "vigentes_hoy": vigentes,
        "por_vencer": por_vencer,
        "vencidos": vencidos,
    }


def evidencias_para_evaluacion_consulta(
    evidencias: dict[tuple[str, str], list[Any]],
) -> dict[tuple[str, str], list[Any]]:
    """Para radar/vencimientos: ignora propuesta vigente si hay sucedida confirmada en el mismo requisito."""
    from app.core.estado_documental import EvidenciaDocumental

    salida: dict[tuple[str, str], list[Any]] = {}
    for clave, lista in evidencias.items():
        vigentes = [e for e in lista if e.estado_version.value == "vigente"]
        sucedidas = [e for e in lista if e.estado_version.value == "sucedida"]
        if (
            len(vigentes) == 1
            and vigentes[0].estado_confirmacion.value == "declarado"
            and sucedidas
        ):
            salida[clave] = list(sucedidas) + [e for e in vigentes if False]
            continue
        salida[clave] = list(lista)
    return salida
