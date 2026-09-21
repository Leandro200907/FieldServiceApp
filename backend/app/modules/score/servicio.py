"""Score de salud documental (anexo "Alcance de la v1": "número que el gerente entiende en
dos segundos"; capa de reporting sobre el mismo dato ya evaluado).

Definición cerrada (DECISIONES §16): para cada sujeto activo, los requisitos EXIGIDOS son
las definiciones que aparecen en alguna línea de matriz vigente hoy para su tipo de
sujeto (más los requisitos particulares de OC activas); un requisito está CUBIERTO si hay
evidencia vigente hoy y verificada (declarado no cuenta, 1.10) o una constancia del
cliente vigente. score = cubiertos / exigidos × 100, global y por tipo de sujeto, con
los sujetos de peor cobertura. Se calcula a pedido (consulta) y el worker guarda un
snapshot diario (cola `score_documental`) para tener historial.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.alcance import alcance_de_sujetos
from app.auth.identidad import Identidad, Rol
from app.comun.reloj import hoy_del_tenant

_SQL = """
WITH exigidos AS (
    SELECT DISTINCT l.requisito_definicion_id, r.tipo_sujeto_aplicable
    FROM modulo1.linea_requisito l
    JOIN modulo1.matriz_requisitos m ON m.tenant_id = l.tenant_id AND m.matriz_version_id = l.matriz_version_id
    JOIN modulo1.definicion_requisito r ON r.tenant_id = l.tenant_id AND r.requisito_definicion_id = l.requisito_definicion_id
    WHERE l.tenant_id = :t AND r.activa AND m.vigente_desde <= :hoy AND (m.vigente_hasta IS NULL OR m.vigente_hasta >= :hoy)
    UNION
    SELECT DISTINCT p.requisito_definicion_id, r.tipo_sujeto_aplicable
    FROM modulo1.requisito_particular p
    JOIN modulo1.oc o ON o.tenant_id = p.tenant_id AND o.clave_origen = p.commitment_id
    JOIN modulo1.definicion_requisito r ON r.tenant_id = p.tenant_id AND r.requisito_definicion_id = p.requisito_definicion_id
    WHERE p.tenant_id = :t AND o.estado = 'activo' AND r.activa
),
cubiertos AS (
    SELECT sujeto_id, requisito_definicion_id FROM modulo1.documento
    WHERE tenant_id = :t AND estado_version = 'vigente' AND estado_confirmacion <> 'declarado' AND vigente_desde <= :hoy AND vigente_hasta >= :hoy
    UNION SELECT persona_id, requisito_definicion_id FROM modulo1.acreditacion_competencia
    WHERE tenant_id = :t AND estado_confirmacion <> 'declarado' AND vigente_desde <= :hoy AND vigente_hasta >= :hoy
    UNION SELECT persona_id, requisito_definicion_id FROM modulo1.induccion
    WHERE tenant_id = :t AND estado_confirmacion <> 'declarado' AND vigente_desde <= :hoy AND vigente_hasta >= :hoy
    UNION SELECT sujeto_id, requisito_definicion_id FROM modulo1.constancia_cliente
    WHERE tenant_id = :t AND estado = 'vigente' AND (vigencia IS NULL OR vigencia >= :hoy)
)
SELECT s.sujeto_id, s.tipo_sujeto, count(e.requisito_definicion_id) AS exigidos,
       count(c.requisito_definicion_id) AS cubiertos
FROM modulo1.legajo s
LEFT JOIN exigidos e ON e.tipo_sujeto_aplicable = s.tipo_sujeto
LEFT JOIN cubiertos c ON c.sujeto_id = s.sujeto_id AND c.requisito_definicion_id = e.requisito_definicion_id
WHERE s.tenant_id = :t AND s.dado_de_baja_en IS NULL {filtro}
GROUP BY s.sujeto_id, s.tipo_sujeto
ORDER BY s.tipo_sujeto, s.sujeto_id
"""


def calcular(session: Session, tenant_id: str, hoy: date, alcance: list[str] | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"t": tenant_id, "hoy": hoy}
    filtro = ""
    if alcance is not None:
        filtro = " AND s.sujeto_id = ANY(CAST(:alcance AS text[]))"
        params["alcance"] = alcance
    filas = [dict(f) for f in session.execute(text(_SQL.format(filtro=filtro)), params).mappings()]
    exigidos = sum(f["exigidos"] for f in filas)
    cubiertos = sum(f["cubiertos"] for f in filas)
    por_tipo: dict[str, dict[str, int]] = {}
    for f in filas:
        d = por_tipo.setdefault(f["tipo_sujeto"], {"sujetos": 0, "exigidos": 0, "cubiertos": 0})
        d["sujetos"] += 1
        d["exigidos"] += f["exigidos"]
        d["cubiertos"] += f["cubiertos"]
    pct = lambda c, e: round(100.0 * c / e, 2) if e else 100.0  # noqa: E731
    peores = sorted((f for f in filas if f["exigidos"]), key=lambda f: (pct(f["cubiertos"], f["exigidos"]), f["sujeto_id"]))[:10]
    return {
        "fecha": hoy.isoformat(), "score": pct(cubiertos, exigidos), "exigidos": exigidos, "cubiertos": cubiertos,
        "sujetos": len(filas), "sujetos_completos": sum(1 for f in filas if f["exigidos"] and f["cubiertos"] == f["exigidos"]),
        "por_tipo_sujeto": {k: {**v, "score": pct(v["cubiertos"], v["exigidos"])} for k, v in por_tipo.items()},
        "peores": [{"sujeto_id": f["sujeto_id"], "tipo_sujeto": f["tipo_sujeto"], "exigidos": f["exigidos"], "cubiertos": f["cubiertos"],
                    "score": pct(f["cubiertos"], f["exigidos"])} for f in peores],
    }


def consulta(session: Session, identidad: Identidad) -> dict[str, Any]:
    """Score actual (alcance por rol) + historial de snapshots del tenant (últimos 90)."""
    identidad.exigir_rol(Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    actual = calcular(session, identidad.tenant_id, hoy, alcance_de_sujetos(session, identidad, hoy))
    historial = [{"fecha": f["fecha"].isoformat(), "score": float(f["score"]), "exigidos": f["exigidos"], "cubiertos": f["cubiertos"]}
                 for f in session.execute(text("SELECT fecha, score, exigidos, cubiertos FROM modulo1.score_snapshot WHERE tenant_id = :t ORDER BY fecha DESC LIMIT 90"),
                                          {"t": identidad.tenant_id}).mappings()]
    return {**actual, "historial": historial}


def guardar_snapshot(session: Session, tenant_id: str, ahora: datetime) -> dict[str, Any]:
    """Handler de la cola `score_documental`: snapshot del día (idempotente por fecha)."""
    hoy = hoy_del_tenant(session, tenant_id, ahora)
    r = calcular(session, tenant_id, hoy)
    session.execute(text(
        "INSERT INTO modulo1.score_snapshot (tenant_id, fecha, score, exigidos, cubiertos, detalle, calculado_en) VALUES (:t, :f, :s, :e, :c, CAST(:d AS jsonb), :ahora) "
        "ON CONFLICT (tenant_id, fecha) DO UPDATE SET score = EXCLUDED.score, exigidos = EXCLUDED.exigidos, cubiertos = EXCLUDED.cubiertos, detalle = EXCLUDED.detalle, calculado_en = EXCLUDED.calculado_en"),
        {"t": tenant_id, "f": hoy, "s": r["score"], "e": r["exigidos"], "c": r["cubiertos"], "d": json.dumps(r, default=str), "ahora": ahora})
    return {"fecha": hoy.isoformat(), "score": r["score"]}


def encolar_snapshot_diario(session: Session, tenant_id: str, ahora: datetime) -> dict[str, int]:
    """Reloj: un job `score_documental` por tenant y día (dedup por fecha en el payload).
    `disponible_en=ahora`, no el default de `encolar` (`now()` de la base): el job tiene
    que quedar disponible para ESTE tick del reloj, sea real o controlado (tests, replay,
    corridas con reloj adelantado/atrasado)."""
    from app.worker.cola import encolar

    hoy = hoy_del_tenant(session, tenant_id, ahora)
    ya = session.execute(text("SELECT 1 FROM modulo1.job_queue WHERE tenant_id = :t AND cola = 'score_documental' AND payload->>'fecha' = :f"),
                         {"t": tenant_id, "f": hoy.isoformat()}).first()
    if ya:
        return {"score_jobs": 0}
    encolar(session, "score_documental", {"fecha": hoy.isoformat()}, tenant_id=tenant_id, disponible_en=ahora)
    return {"score_jobs": 1}
