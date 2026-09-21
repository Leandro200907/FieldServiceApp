"""Aviso de incumplimiento de empresa (2.9 de modelo-dominio; 7.1 `CumplimientoEmpresaAfectado`).

- Un aviso abierto por tenant (único parcial). Se abre con la primera causa (un requisito
  de empresa cuyo documento vigente está vencido) y emite UNA vez el outbox
  `CumplimientoEmpresaAfectado` (clave_dedup `cea:{aviso_id}`), con payload flaco: el
  consumidor consulta el estado actual (`GET /consultas/incumplimiento_empresa`).
- Cada requisito incumplido es una causa `activa` (una activa por aviso/requisito, único
  parcial); nuevas causas se suman sin repetir el evento; las regularizadas quedan como
  auditoría.
- Marca internamente las decisiones vigentes del tenant (aviso de revaluación con esta
  causa, SIN HabilitacionRequiereRevaluacion a outbox — 2.9: "en lote, prolijidad").
- Se REGULARIZA solo cuando una reevaluación de TODAS las causas activas determina que
  ninguna sigue incumplida (hay documento de empresa vigente y verificado para cada
  requisito). Regularizar A con B pendiente deja el aviso abierto con B. La reevaluación
  bloquea la fila del aviso (FOR UPDATE) para que dos regularizaciones concurrentes no se
  pisen ni dejen el aviso abierto por error.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.comun.eventos import encolar_outbox, registrar_evento_interno
from app.comun.reloj import ahora_utc

_SQL_REQUISITOS_EMPRESA_INCUMPLIDOS = """
    SELECT r.requisito_definicion_id, l.sujeto_id,
           (SELECT max(d.vigente_hasta) FROM modulo1.documento d
             WHERE d.tenant_id = :t AND d.sujeto_id = l.sujeto_id AND d.requisito_definicion_id = r.requisito_definicion_id
               AND d.estado_version = 'vigente' AND d.estado_confirmacion <> 'declarado') AS vigente_hasta
    FROM modulo1.definicion_requisito r
    CROSS JOIN (SELECT sujeto_id FROM modulo1.legajo WHERE tenant_id = :t AND tipo_sujeto = 'empresa'
                AND dado_de_baja_en IS NULL ORDER BY creado_en LIMIT 1) l
    WHERE r.tenant_id = :t AND r.tipo_sujeto_aplicable = 'empresa' AND r.activa
"""


def registrar_vencimientos_de_empresa(session: Session, tenant_id: str, hoy: date) -> dict[str, Any]:
    """Proceso de reloj: detecta requisitos de empresa con documento vencido (vigente_hasta <
    hoy, o sin documento verificado) SOLO cuando antes hubo un documento (vencimiento, no
    ausencia inicial) y los registra como causas activas del aviso abierto del tenant."""
    filas = session.execute(text(_SQL_REQUISITOS_EMPRESA_INCUMPLIDOS), {"t": tenant_id}).mappings().all()
    vencidos = [f for f in filas if f["vigente_hasta"] is not None and f["vigente_hasta"] < hoy]
    if not vencidos:
        return {"causas_nuevas": 0, "aviso_abierto": False}
    fila = session.execute(
        text("INSERT INTO modulo1.aviso_incumplimiento_empresa (tenant_id, desde) VALUES (:t, :d) "
             "ON CONFLICT (tenant_id) WHERE estado = 'abierto' DO NOTHING RETURNING aviso_id"),
        {"t": tenant_id, "d": min(f["vigente_hasta"] for f in vencidos)},
    ).first()
    abierto_ahora = fila is not None
    aviso_id = str(fila[0]) if fila else str(session.execute(
        text("SELECT aviso_id FROM modulo1.aviso_incumplimiento_empresa WHERE tenant_id = :t AND estado = 'abierto' FOR UPDATE"),
        {"t": tenant_id},
    ).scalar())
    nuevas = 0
    for f in vencidos:
        insertada = session.execute(
            text("INSERT INTO modulo1.aviso_incumplimiento_empresa_causa (tenant_id, aviso_id, requisito_definicion_id, desde) "
                 "VALUES (:t, :a, :r, :d) ON CONFLICT (tenant_id, aviso_id, requisito_definicion_id) WHERE estado = 'activa' "
                 "DO NOTHING RETURNING causa_id"),
            {"t": tenant_id, "a": aviso_id, "r": str(f["requisito_definicion_id"]), "d": f["vigente_hasta"]},
        ).first()
        nuevas += 1 if insertada else 0
    if abierto_ahora:
        evento_id = registrar_evento_interno(
            session, tenant_id, "CumplimientoEmpresaAfectado",
            {"aviso_id": aviso_id, "desde": min(f["vigente_hasta"] for f in vencidos).isoformat(), "causas_iniciales": nuevas},
            usuario_id=None,
        )
        encolar_outbox(
            session, tenant_id, "CumplimientoEmpresaAfectado",
            {"aviso_id": aviso_id, "desde": min(f["vigente_hasta"] for f in vencidos).isoformat(),
             "emitido_en": ahora_utc().isoformat()},
            clave_dedup=f"cea:{aviso_id}",
        )
        # Marca interna de las decisiones vigentes del tenant, sin fan-out a Módulo 2 (2.9).
        from app.core.revaluacion import _vigentes, abrir_o_sumar_aviso

        for d in _vigentes(session, tenant_id, hoy):
            abrir_o_sumar_aviso(
                session, tenant_id, str(d["referencia_evaluacion"]), d["commitment_id"], evento_id,
                "CumplimientoEmpresaAfectado", "aviso_incumplimiento_empresa", aviso_id, emitir_outbox=False,
            )
    return {"causas_nuevas": nuevas, "aviso_abierto": abierto_ahora, "aviso_id": aviso_id}


def reevaluar_causas(session: Session, tenant_id: str, hoy: date) -> dict[str, Any]:
    """Reevalúa TODAS las causas activas del aviso abierto; regulariza las que hoy tienen
    documento de empresa vigente y verificado; cierra el aviso solo si no queda ninguna."""
    aviso_id = session.execute(
        text("SELECT aviso_id FROM modulo1.aviso_incumplimiento_empresa WHERE tenant_id = :t AND estado = 'abierto' FOR UPDATE"),
        {"t": tenant_id},
    ).scalar()
    if aviso_id is None:
        return {"aviso": None, "regularizadas": 0, "cerrado": False}
    estado_req = {
        str(f["requisito_definicion_id"]): (f["vigente_hasta"] is not None and f["vigente_hasta"] >= hoy)
        for f in session.execute(text(_SQL_REQUISITOS_EMPRESA_INCUMPLIDOS), {"t": tenant_id}).mappings()
    }
    activas = session.execute(
        text("SELECT causa_id, requisito_definicion_id FROM modulo1.aviso_incumplimiento_empresa_causa "
             "WHERE tenant_id = :t AND aviso_id = :a AND estado = 'activa'"),
        {"t": tenant_id, "a": aviso_id},
    ).mappings().all()
    regularizadas = 0
    for c in activas:
        if estado_req.get(str(c["requisito_definicion_id"]), False):
            regularizadas += session.execute(
                text("UPDATE modulo1.aviso_incumplimiento_empresa_causa SET estado = 'regularizada', regularizada_en = now() "
                     "WHERE tenant_id = :t AND causa_id = :c AND estado = 'activa'"),
                {"t": tenant_id, "c": c["causa_id"]},
            ).rowcount
    cerrado = session.execute(
        text("UPDATE modulo1.aviso_incumplimiento_empresa SET estado = 'regularizado', regularizado_en = now() "
             "WHERE tenant_id = :t AND aviso_id = :a AND estado = 'abierto' AND NOT EXISTS ("
             "  SELECT 1 FROM modulo1.aviso_incumplimiento_empresa_causa c WHERE c.tenant_id = :t AND c.aviso_id = :a AND c.estado = 'activa')"),
        {"t": tenant_id, "a": aviso_id},
    ).rowcount == 1
    if cerrado:
        registrar_evento_interno(session, tenant_id, "CumplimientoEmpresaRegularizado", {"aviso_id": str(aviso_id)}, usuario_id=None)
    return {"aviso": str(aviso_id), "regularizadas": regularizadas, "cerrado": cerrado}


def estado_actual(session: Session, tenant_id: str) -> dict[str, Any] | None:
    """Vista para el consumidor: aviso abierto + causas (JSON derivado de las filas)."""
    aviso = session.execute(
        text("SELECT aviso_id, estado, desde, abierto_en, regularizado_en FROM modulo1.aviso_incumplimiento_empresa "
             "WHERE tenant_id = :t ORDER BY abierto_en DESC LIMIT 1"),
        {"t": tenant_id},
    ).mappings().first()
    if aviso is None:
        return None
    causas = session.execute(
        text("SELECT c.causa_id, c.requisito_definicion_id, r.nombre, c.estado, c.desde, c.registrada_en, c.regularizada_en "
             "FROM modulo1.aviso_incumplimiento_empresa_causa c "
             "LEFT JOIN modulo1.definicion_requisito r ON r.requisito_definicion_id = c.requisito_definicion_id "
             "WHERE c.tenant_id = :t AND c.aviso_id = :a ORDER BY c.registrada_en"),
        {"t": tenant_id, "a": aviso["aviso_id"]},
    ).mappings().all()
    return {
        "aviso_id": str(aviso["aviso_id"]), "estado": aviso["estado"], "desde": aviso["desde"],
        "abierto_en": aviso["abierto_en"], "regularizado_en": aviso["regularizado_en"],
        "causas": [{**dict(c), "causa_id": str(c["causa_id"]), "requisito_definicion_id": str(c["requisito_definicion_id"])} for c in causas],
        "causas_activas": [str(c["requisito_definicion_id"]) for c in causas if c["estado"] == "activa"],
    }
