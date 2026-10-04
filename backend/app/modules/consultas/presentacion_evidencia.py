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
    "sin_archivo_respaldo",
    "propuesta_en_revision",
)

EXPLICACION_ESTADO: dict[str, str] = {
    "verificada": "La evidencia está confirmada y vigente dentro de su período.",
    "declarada": "Hay datos cargados que aún no fueron verificados por un responsable.",
    "por_vencer": "La evidencia sigue vigente pero vence dentro del plazo de aviso configurado.",
    "vencida": "La fecha de vigencia ya pasó; hace falta renovar o reemplazar la evidencia.",
    "archivo_en_revision": "Archivo en verificación técnica; el worker está validando formato e integridad.",
    "evidencia_invalida": "El archivo fue rechazado en la validación; hay que subir una evidencia nueva.",
    "sin_archivo_respaldo": "No hay archivo de respaldo cargado para esta evidencia.",
    "propuesta_en_revision": "Un técnico propuso una renovación que espera confirmación; no reemplaza la versión vigente.",
}


def _archivo_validacion_de_fila(fila: Mapping[str, Any]) -> str:
    archivo_estado = fila.get("archivo_estado")
    clave = fila.get("clave_storage")
    if archivo_estado == "sin_archivo" or (clave is None and archivo_estado != "confirmado"):
        return "sin_archivo"
    if archivo_estado == "confirmado":
        if fila.get("archivo_validacion") is not None:
            return str(fila["archivo_validacion"])
        return "pendiente"
    if clave is None:
        return "sin_archivo"
    return "pendiente"


def _es_propuesta_pendiente(fila: Mapping[str, Any]) -> bool:
    return fila.get("estado_version") == "propuesta" and fila.get("estado_confirmacion") == "declarado"


def _plazo_aviso(plazo_requisito: int | None, plazo_tenant: int) -> int:
    return plazo_requisito if plazo_requisito is not None else plazo_tenant


def estado_vigencia_presentacion(
    hoy: date,
    *,
    vigente_hasta: date | None,
    vencido: bool,
    plazo_aviso_dias: int,
) -> str:
    """Solo vigencia por fechas; la confirmación va en estados_adicionales."""
    if vencido:
        return "vencida"
    if vigente_hasta is not None and (vigente_hasta - hoy).days <= plazo_aviso_dias:
        return "por_vencer"
    return "verificada"


def estado_respaldo_presentacion(archivo_validacion: str) -> str | None:
    if archivo_validacion == "sin_archivo":
        return "sin_archivo_respaldo"
    if archivo_validacion == "pendiente":
        return "archivo_en_revision"
    if archivo_validacion == "invalido":
        return "evidencia_invalida"
    return None


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
    estado = estado_vigencia_presentacion(
        hoy,
        vigente_hasta=hasta,
        vencido=vencido,
        plazo_aviso_dias=plazo,
    )
    respaldo = estado_respaldo_presentacion(archivo)
    adicionales: list[str] = [respaldo] if respaldo else []
    if str(fila.get("estado_confirmacion") or "") == "declarado":
        adicionales.append("declarada")
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


def mapa_ultimos_rechazos_propuesta(session: Session, tenant_id: str, sujeto_id: str) -> dict[str, dict[str, Any]]:
    """Último motivo de rechazo de propuesta por requisito (event_log DocumentoRechazado)."""
    from sqlalchemy import text

    filas = session.execute(
        text(
            """
            SELECT d.requisito_definicion_id::text AS requisito_definicion_id,
                   e.payload->>'motivo' AS motivo,
                   e.ocurrido_en
            FROM modulo1.documento d
            JOIN modulo1.event_log e ON e.tenant_id = d.tenant_id
              AND e.tipo = 'DocumentoRechazado'
              AND e.payload->>'documento_id' = d.documento_id::text
            WHERE d.tenant_id = :t AND d.sujeto_id = :sj
              AND d.estado_version = 'rechazada' AND d.origen_propuesta
            ORDER BY e.ocurrido_en DESC
            """
        ),
        {"t": tenant_id, "sj": sujeto_id},
    ).mappings().all()
    salida: dict[str, dict[str, Any]] = {}
    for f in filas:
        rid = str(f["requisito_definicion_id"])
        if rid in salida:
            continue
        rechazado_en = f["ocurrido_en"]
        salida[rid] = {
            "motivo": f["motivo"],
            "rechazado_en": rechazado_en.isoformat() if hasattr(rechazado_en, "isoformat") else str(rechazado_en),
        }
    return salida


def adjuntar_ultimos_rechazos_propuesta(
    session: Session,
    tenant_id: str,
    sujeto_id: str,
    items: list[dict[str, Any]],
) -> None:
    rechazos = mapa_ultimos_rechazos_propuesta(session, tenant_id, sujeto_id)
    for item in items:
        if item.get("propuesta_en_revision"):
            continue
        rid = str(item.get("requisito_definicion_id") or "")
        if rid and rid in rechazos:
            item["ultimo_rechazo_propuesta"] = rechazos[rid]


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
                   l.identificador_natural, l.nombre_apellido, l.tipo_sujeto
            FROM modulo1.documento d
            LEFT JOIN modulo1.definicion_requisito r
              ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
            LEFT JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id
            WHERE d.tenant_id = :t AND d.sujeto_id = :s
              AND d.estado_version IN ('vigente', 'sucedida', 'propuesta')
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
        propuesta = next((g for g in grupo if g["estado_version"] == "propuesta"), None)
        if vigente is not None:
            base = _fila_con_vigencia(vigente, hoy)
            base = enriquecer_fila_evidencia(base, hoy, plazo_tenant)
            if propuesta is not None and _es_propuesta_pendiente(propuesta):
                base["propuesta_en_revision"] = {
                    "documento_id": str(propuesta["id"]),
                    "vigente_desde": propuesta["vigente_desde"].isoformat() if propuesta.get("vigente_desde") else None,
                    "vigente_hasta": propuesta["vigente_hasta"].isoformat() if propuesta.get("vigente_hasta") else None,
                    "estado_presentacion": "propuesta_en_revision",
                    "estado_presentacion_explicacion": EXPLICACION_ESTADO["propuesta_en_revision"],
                }
            salida.append(base)
            continue
        if propuesta is not None and _es_propuesta_pendiente(propuesta):
            base = _fila_con_vigencia(propuesta, hoy)
            base = enriquecer_fila_evidencia(base, hoy, plazo_tenant)
            base["estado_presentacion"] = "propuesta_en_revision"
            base["estado_presentacion_explicacion"] = EXPLICACION_ESTADO["propuesta_en_revision"]
            salida.append(base)
    salida.sort(key=lambda i: (i.get("vigente_hasta") or "", i.get("tipo") or "", i.get("requisito") or ""))
    adjuntar_ultimos_rechazos_propuesta(session, tenant_id, sujeto_id, salida)
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


def _cuenta_como_en_regla_hoy(item: dict[str, Any]) -> bool:
    """D19: solo verificado/confirmado_en_fuente con respaldo válido habilita para el resumen."""
    if item.get("estado_presentacion") == "propuesta_en_revision":
        return False
    if not item.get("vigente_hoy"):
        return False
    if item.get("estado_confirmacion") not in ("verificado", "confirmado_en_fuente"):
        return False
    if item.get("archivo_validacion") != "valido":
        return False
    return True


def adjuntar_rechazos_operadora(session: Session, tenant_id: str, items: list[dict[str, Any]]) -> None:
    """E-10: rechazo en ficha / mi legajo (texto corto por operadora)."""
    from app.core.consulta_documental import cargar_entregas_operadora

    entregas = cargar_entregas_operadora(session, tenant_id)
    for item in items:
        doc_id = str(item.get("id") or "")
        if not doc_id:
            continue
        rechazos = [
            entrega
            for (_op, did), entrega in entregas.items()
            if did == doc_id and str(entrega.get("estado") or "") == "rechazado"
        ]
        if not rechazos:
            continue
        nombre = str(rechazos[0].get("operadora_nombre") or "la operadora")
        item["observacion_operadora"] = f"Rechazado por {nombre}"


def resumen_desde_items(items: list[dict[str, Any]]) -> dict[str, int]:
    vigentes = por_vencer = vencidos = 0
    for i in items:
        est = i.get("estado_presentacion")
        if est == "vencida" or i.get("vencido"):
            vencidos += 1
        elif est == "por_vencer":
            por_vencer += 1
        elif est in ("verificada", "declarada"):
            if _cuenta_como_en_regla_hoy(i):
                vigentes += 1
    return {
        "total": len(items),
        "vigentes_hoy": vigentes,
        "por_vencer": por_vencer,
        "vencidos": vencidos,
    }

