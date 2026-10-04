"""Evaluación documental compartida del Módulo 1 (consulta).

Centraliza espejo por operadora (E-10), ventana desde hoy (D23), fecha de bloqueo,
clasificación vencido vs. sin documento y estado agregado de la OC para Radar y Backlog.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.estado_documental import (
    EstadoRequisitoDocumental,
    EvaluacionDocumentalEntrada,
    ResultadoRequisitoDocumental,
    evaluar_requisito_documental,
)
from app.core.radar_documental import ResumenDocumental, resumir_oc, resumir_resultados


def _as_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _formatear_fecha_civil(valor: datetime | date | str | None) -> str:
    if valor is None:
        return "fecha no informada"
    if isinstance(valor, datetime):
        return valor.date().strftime("%d/%m/%Y")
    d = _as_date(valor)
    return d.strftime("%d/%m/%Y") if d else ""


def cargar_entregas_operadora(session: Session, tenant_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    """(operadora_id, documento_id) → fila de entrega_documento_operadora."""
    filas = session.execute(
        text(
            """
            SELECT e.operadora_id::text, e.documento_id::text, e.estado, e.rechazado_en,
                   o.nombre AS operadora_nombre
            FROM modulo1.entrega_documento_operadora e
            JOIN modulo1.operadora_documental o
              ON o.tenant_id = e.tenant_id AND o.operadora_id = e.operadora_id
            WHERE e.tenant_id = :t
            """
        ),
        {"t": tenant_id},
    ).mappings().all()
    return {(str(f["operadora_id"]), str(f["documento_id"])): dict(f) for f in filas}


def cargar_propuestas_pendientes(session: Session, tenant_id: str) -> set[tuple[str, str]]:
    filas = session.execute(
        text(
            """
            SELECT sujeto_id, requisito_definicion_id::text
            FROM modulo1.documento
            WHERE tenant_id = :t AND estado_version = 'propuesta' AND estado_confirmacion = 'declarado'
            """
        ),
        {"t": tenant_id},
    ).all()
    return {(str(s), str(r)) for s, r in filas}


def ventana_evaluacion_oc(hoy: date, oc: Mapping[str, Any], *, hasta_filtro: date | None = None) -> tuple[date, date]:
    """Período inclusivo de evaluación: desde hoy (D23) hasta el fin de la OC o del filtro."""
    fin_oc = _as_date(oc["vigencia_hasta"])
    inicio_oc = _as_date(oc["vigencia_desde"])
    assert fin_oc is not None and inicio_oc is not None
    inicio = max(hoy, inicio_oc)
    fin = fin_oc
    if hasta_filtro is not None:
        fin = min(fin, hasta_filtro)
    return inicio, fin


def ajustar_por_espejo_operadora(
    resultado: ResultadoRequisitoDocumental,
    *,
    operadora_id: str | None,
    operadora_nombre: str,
    entregas: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[ResultadoRequisitoDocumental, str | None, str | None]:
    """E-10: rechazo bloquea; pendientes solo avisan. Devuelve (resultado, aviso_espejo, accion)."""
    evidencia_id = resultado.evidencia_id
    if not operadora_id or not evidencia_id:
        return resultado, None, None
    entrega = entregas.get((str(operadora_id), str(evidencia_id)))
    if entrega is None:
        return resultado, "pendiente_envio", None
    estado_ent = str(entrega.get("estado") or "")
    if estado_ent == "aceptado":
        return resultado, None, None
    if estado_ent == "rechazado":
        nombre = str(entrega.get("operadora_nombre") or operadora_nombre or "la operadora")
        fecha_txt = _formatear_fecha_civil(entrega.get("rechazado_en"))
        motivo = f"Rechazado por {nombre} el {fecha_txt}".strip()
        accion = f"Regularizar ante {nombre}"
        bloqueado = ResultadoRequisitoDocumental(
            estado=EstadoRequisitoDocumental.FALTANTE,
            primer_quiebre=resultado.primer_quiebre,
            evidencia_id=evidencia_id,
            motivo=motivo,
            accion_sugerida=accion,
            accion_sugerida_fecha=resultado.accion_sugerida_fecha,
        )
        return bloqueado, "rechazado", accion
    if estado_ent in ("exportado", "enviado"):
        return resultado, "pendiente_aceptacion", None
    return resultado, None, None


def evaluar_requisito_en_oc(
    entrada: EvaluacionDocumentalEntrada,
    *,
    operadora_id: str | None,
    operadora_nombre: str,
    entregas: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[ResultadoRequisitoDocumental, str | None, str | None]:
    """Resolución de evidencia ya aplicada en `entrada.evidencias`; evalúa y aplica espejo (E-10)."""
    base = evaluar_requisito_documental(entrada)
    return ajustar_por_espejo_operadora(
        base,
        operadora_id=operadora_id,
        operadora_nombre=operadora_nombre,
        entregas=entregas,
    )


def clasificar_problema_documental(req: Mapping[str, Any]) -> str | None:
    """E-64/E-70: «vencido» vs «sin_documento» para etiquetas de acción y radar."""
    if req.get("es_rechazo_operadora"):
        return "rechazo_operadora"
    estado = req.get("estado")
    evidencia_id = req.get("evidencia_id")
    if estado == EstadoRequisitoDocumental.FALTANTE.value and not evidencia_id:
        return "sin_documento"
    if estado in (
        EstadoRequisitoDocumental.VENCIDO_ANTES_INICIO.value,
        EstadoRequisitoDocumental.VENCE_DURANTE_PERIODO.value,
    ):
        return "vencido"
    if estado == EstadoRequisitoDocumental.FALTANTE.value:
        return "sin_documento"
    if estado == EstadoRequisitoDocumental.EVIDENCIA_INVALIDA.value:
        return "vencido"
    return None


def fecha_desde_cuando_bloquea(
    hoy: date,
    oc: Mapping[str, Any],
    req: Mapping[str, Any],
    fallback: date,
) -> date:
    """Única regla para Radar y acciones pendientes (E-64, D23)."""
    inicio_oc = _as_date(oc["vigencia_desde"]) or fallback
    inicio = max(hoy, inicio_oc)
    pq = req.get("primer_quiebre")
    if pq:
        pq_d = _as_date(pq) or fallback
        if pq_d <= hoy:
            return inicio
        return pq_d
    vh = req.get("vigente_hasta")
    if vh:
        vh_d = _as_date(vh) or fallback
        candidato = vh_d + timedelta(days=1)
        if candidato <= hoy:
            return inicio
        return candidato
    fb = _as_date(fallback) or hoy
    return max(inicio, fb)


def etiqueta_bloqueo_desde(hoy: date, fecha_bloqueo: date) -> str:
    if fecha_bloqueo <= hoy:
        return "Ya bloquea"
    return f"Bloquea desde {fecha_bloqueo.strftime('%d/%m/%Y')}"


def accion_sugerida_para_req(
    req: Mapping[str, Any],
    *,
    propuestas_pendientes: set[tuple[str, str]],
    sujeto_id: str,
    requisito_definicion_id: str,
) -> str | None:
    """E-35 / E-70: acción corta sin fecha ni nombre de requisito."""
    if (sujeto_id, requisito_definicion_id) in propuestas_pendientes:
        return "Revisar propuesta"
    accion = req.get("accion_sugerida")
    if accion and str(accion).startswith("Regularizar ante"):
        return str(accion)
    problema = clasificar_problema_documental(req)
    if problema == "sin_documento":
        return "Incorporar documento"
    if problema == "rechazo_operadora" and accion:
        return str(accion)
    if req.get("accion_sugerida"):
        texto = str(req["accion_sugerida"])
        if "Renovar" in texto or "renovar" in texto:
            return "Renovar"
        if "Incorporar" in texto or "incorporar" in texto:
            return "Incorporar documento"
        if "Revisar" in texto:
            return "Revisar propuesta"
    return None


def estado_documental_de_oc(
    session: Session,
    tenant_id: str,
    oc: Mapping[str, Any],
    legajos: list[dict[str, Any]],
    evidencias: dict[tuple[str, str], list[Any]],
    hoy: date,
    *,
    hasta: date | None = None,
    tipos_fuera_de_alcance: list[str] | None = None,
    entregas: dict[tuple[str, str], dict[str, Any]] | None = None,
    hasta_filtro: date | None = None,
) -> ResumenDocumental:
    """Estado agregado único para Radar y Backlog (E-21)."""
    from app.modules.proyeccion import radar as radar_mod

    entregas = entregas if entregas is not None else cargar_entregas_operadora(session, tenant_id)
    fin_filtro = hasta_filtro if hasta_filtro is not None else hasta
    inicio, fin = ventana_evaluacion_oc(hoy, oc, hasta_filtro=fin_filtro)
    operadora_id = str(oc.get("cliente_id") or "")
    nombres = session.execute(
        text("SELECT operadora_id::text, nombre FROM modulo1.operadora_documental WHERE tenant_id = :t"),
        {"t": tenant_id},
    ).mappings().all()
    nombre_op = next((n["nombre"] for n in nombres if str(n["operadora_id"]) == operadora_id), "")

    tramos, _, huecos_matriz = radar_mod._matrices_y_requisitos(session, tenant_id, dict(oc), inicio, fin)
    if huecos_matriz and not tramos:
        return ResumenDocumental("sin_matriz", None, 0, 0)

    calculo = radar_mod._evaluar_oc(
        session,
        tenant_id,
        dict(oc),
        legajos,
        evidencias,
        inicio,
        fin,
        tipos_fuera_de_alcance=tipos_fuera_de_alcance,
        entregas=entregas,
        operadora_id=operadora_id,
        operadora_nombre=nombre_op,
    )
    return calculo["estado"]


def resumen_legajo_con_en_regla(items: list[dict[str, Any]]) -> dict[str, int]:
    from app.modules.consultas.presentacion_evidencia import _cuenta_como_en_regla_hoy, resumen_desde_items

    base = resumen_desde_items(items)
    en_regla = sum(1 for i in items if _cuenta_como_en_regla_hoy(i))
    base["en_regla"] = en_regla
    ocs: set[str] = set()
    for item in items:
        for oc in item.get("ocs_afectadas") or []:
            clave = str(oc.get("oc_id") or oc.get("clave_origen") or "")
            if clave:
                ocs.add(clave)
    base["ocs_afectadas"] = len(ocs)
    return base
