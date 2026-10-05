"""Requisitos exigidos al sujeto por matrices del backlog (unión de OC, misma evaluación que Radar)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.auth.identidad import Identidad
from app.comun.reloj import hoy_del_tenant
from app.modules.consultas.ocs_afectadas import (
    ordenar_ocs_afectadas,
    referencia_oc,
    requisito_sin_cobertura_en_periodo,
)


def _tipo_lista_desde_categoria(categoria: str | None) -> str:
    if categoria == "competencia":
        return "acreditacion"
    if categoria == "induccion":
        return "induccion"
    return "documento"


def _precedencia_estado(estado: str) -> int:
    orden = {
        "faltante": 0,
        "vencido_antes_inicio": 1,
        "evidencia_invalida": 2,
        "pendiente_revision": 3,
        "vence_durante_periodo": 4,
        "vigente_todo_el_periodo": 5,
        "no_evaluable": 2,
        "no_aplica": 6,
    }
    return orden.get(estado, 2)


@dataclass
class AgregadoRequisitoExigido:
    requisito_definicion_id: str
    nombre: str
    categoria: str | None
    tipo: str
    locacion_id: str | None = None
    estado_peor: str = "faltante"
    evidencia_id: str | None = None
    vigente_hasta: date | None = None
    archivo_validacion: str | None = None
    motivo: str | None = None
    sin_cobertura: bool = False
    es_rechazo_operadora: bool = False
    operadora_nombre: str | None = None
    ocs_afectadas: list[dict[str, str]] = field(default_factory=list)

    def actualizar_desde_eval(self, req: dict[str, Any], oc_ref: dict[str, str]) -> None:
        estado = str(req.get("estado") or "faltante")
        if req.get("evidencia_id"):
            self.evidencia_id = str(req["evidencia_id"])
        if _precedencia_estado(estado) < _precedencia_estado(self.estado_peor):
            self.estado_peor = estado
            self.vigente_hasta = req.get("vigente_hasta") or self.vigente_hasta
            self.archivo_validacion = req.get("archivo_validacion") or self.archivo_validacion
            self.motivo = req.get("motivo") or self.motivo
        elif req.get("vigente_hasta") and self.vigente_hasta is None:
            self.vigente_hasta = req.get("vigente_hasta")
        if not self.nombre and req.get("nombre"):
            self.nombre = str(req["nombre"])
        if requisito_sin_cobertura_en_periodo(req):
            self.sin_cobertura = True
            if oc_ref not in self.ocs_afectadas:
                self.ocs_afectadas.append(oc_ref)
        if req.get("es_rechazo_operadora"):
            self.es_rechazo_operadora = True
            motivo = str(req.get("motivo") or "")
            if motivo.startswith("Rechazado por "):
                self.operadora_nombre = motivo.split(" el ", 1)[0].replace("Rechazado por ", "").strip()


def _legajo_minimo(session: Session, tenant_id: str, sujeto_id: str) -> dict[str, Any] | None:
    from sqlalchemy import text

    fila = session.execute(
        text(
            "SELECT sujeto_id, tipo_sujeto, identificador_natural, nombre_apellido "
            "FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = :s AND dado_de_baja_en IS NULL"
        ),
        {"t": tenant_id, "s": sujeto_id},
    ).mappings().first()
    return dict(fila) if fila else None


def agregar_requisitos_exigidos(
    session: Session,
    identidad: Identidad,
    sujeto_id: str,
    *,
    vigencia_desde: date | None = None,
    vigencia_hasta: date | None = None,
) -> dict[str, AgregadoRequisitoExigido]:
    from app.core.consulta_documental import cargar_entregas_operadora, ventana_evaluacion_oc
    from app.core.ventana_backlog import rango_backlog_documental
    from app.modules.proyeccion import radar as radar_mod

    hoy = hoy_del_tenant(session, identidad.tenant_id)
    desde, hasta = rango_backlog_documental(
        session, identidad.tenant_id, hoy, vigencia_desde=vigencia_desde, vigencia_hasta=vigencia_hasta,
    )
    legajo = _legajo_minimo(session, identidad.tenant_id, sujeto_id)
    if legajo is None:
        return {}
    evidencias = radar_mod._evidencias(session, identidad.tenant_id, sujeto_id)
    entregas = cargar_entregas_operadora(session, identidad.tenant_id)
    ocs = radar_mod._ocs(session, identidad.tenant_id, max(desde, hoy), hasta, {}, offset=0, limit=500)
    mapa: dict[str, AgregadoRequisitoExigido] = {}

    for oc in ocs:
        inicio, fin = ventana_evaluacion_oc(hoy, oc, hasta_filtro=min(hasta, oc["vigencia_hasta"]))
        calc = radar_mod._evaluar_oc(
            session,
            identidad.tenant_id,
            oc,
            [legajo],
            evidencias,
            inicio,
            fin,
            entregas=entregas,
            operadora_id=str(oc["cliente_id"]),
        )
        if not calc["legajos"]:
            continue
        reqs = calc["legajos"][0].get("requisitos") or []
        oc_ref = referencia_oc(oc)
        for req in reqs:
            if req.get("requerido") is False:
                continue
            rid = str(req.get("requisito_definicion_id") or "")
            if not rid:
                continue
            if rid not in mapa:
                cat = None
                mapa[rid] = AgregadoRequisitoExigido(
                    requisito_definicion_id=rid,
                    nombre=str(req.get("nombre") or ""),
                    categoria=cat,
                    tipo=_tipo_lista_desde_categoria(cat),
                )
            mapa[rid].actualizar_desde_eval(req, oc_ref)

    from sqlalchemy import text

    if mapa:
        filas = session.execute(
            text(
                "SELECT requisito_definicion_id::text, nombre, categoria, locacion_id::text "
                "FROM modulo1.definicion_requisito WHERE tenant_id = :t AND requisito_definicion_id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"t": identidad.tenant_id, "ids": list(mapa.keys())},
        ).mappings().all()
        for f in filas:
            ag = mapa[str(f["requisito_definicion_id"])]
            ag.nombre = ag.nombre or str(f["nombre"])
            ag.categoria = str(f["categoria"]) if f["categoria"] else ag.categoria
            ag.tipo = _tipo_lista_desde_categoria(ag.categoria)
            ag.locacion_id = str(f["locacion_id"]) if f.get("locacion_id") else None

    for ag in mapa.values():
        ag.ocs_afectadas = ordenar_ocs_afectadas(ag.ocs_afectadas, hoy)
    return mapa


def _es_sin_documento(ag: AgregadoRequisitoExigido) -> bool:
    return ag.estado_peor == "faltante" and not ag.evidencia_id


def _vigente_hasta_date(ag: AgregadoRequisitoExigido) -> date | None:
    vh = ag.vigente_hasta
    if vh is None:
        return None
    if isinstance(vh, date):
        return vh
    return date.fromisoformat(str(vh)[:10])


def _bucket_calendario_exigido(ag: AgregadoRequisitoExigido, hoy: date, plazo_aviso: int) -> str:
    """Tarjetas E-94: solo calendario del papel (rechazo operadora no cuenta como vencido)."""
    if ag.estado_peor in ("vencido_antes_inicio", "evidencia_invalida", "faltante"):
        return "vencidos"
    if ag.estado_peor == "vence_durante_periodo":
        vh = _vigente_hasta_date(ag)
        if vh is not None and vh >= hoy and (vh - hoy).days <= plazo_aviso:
            return "por_vencer"
        return "vencidos"
    if ag.estado_peor == "pendiente_revision":
        return "vencidos"
    return "vigentes"


def _bucket_tarjeta_exigido(ag: AgregadoRequisitoExigido, hoy: date, plazo_aviso: int) -> str:
    if _es_sin_documento(ag):
        return "sin_documento"
    if not ag.sin_cobertura:
        return "vigentes"
    return _bucket_calendario_exigido(ag, hoy, plazo_aviso)


def resumen_exigidos_backlog(
    mapa: dict[str, AgregadoRequisitoExigido],
    hoy: date,
    plazo_aviso: int,
) -> dict[str, int]:
    exigidos = len(mapa)
    en_regla = sum(1 for ag in mapa.values() if not ag.sin_cobertura)
    sin_documento = sum(1 for ag in mapa.values() if _es_sin_documento(ag))
    observados = sum(
        1 for ag in mapa.values() if ag.es_rechazo_operadora and ag.sin_cobertura and not _es_sin_documento(ag)
    )
    buckets = {"vencidos": 0, "por_vencer": 0, "vigentes": 0, "sin_documento": 0}
    for ag in mapa.values():
        buckets[_bucket_tarjeta_exigido(ag, hoy, plazo_aviso)] += 1
    return {
        "exigidos": exigidos,
        "en_regla_exigidos": en_regla,
        "sin_documento": sin_documento,
        "observados_operadora": observados,
        "exigidos_vencidos": buckets["vencidos"],
        "exigidos_por_vencer": buckets["por_vencer"],
        "exigidos_vigentes": buckets["vigentes"],
        "exigidos_sin_documento": buckets["sin_documento"],
    }
