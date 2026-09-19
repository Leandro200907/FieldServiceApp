"""Helpers idempotentes para plantar los PADRES que las FKs compuestas por tenant (0011)
exigen: legajo, OC y evaluación. Todo por SQL directo dentro de la sesión dada."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text


def legajo(s, tenant_id: str, sujeto_id: str, tipo: str = "persona") -> None:
    s.execute(
        text("INSERT INTO modulo1.legajo (tenant_id, sujeto_id, tipo_sujeto, identificador_natural) VALUES (:t, :s, :tipo, :s) "
             "ON CONFLICT DO NOTHING"),
        {"t": tenant_id, "s": sujeto_id, "tipo": tipo},
    )


def oc(s, tenant_id: str, clave: str, desde: date = date(2026, 1, 1), hasta: date = date(2027, 12, 31)) -> None:
    s.execute(
        text("INSERT INTO modulo1.oc (tenant_id, clave_origen, cliente_id, locacion_id, tipo_servicio_id, vigencia_desde, vigencia_hasta) "
             "VALUES (:t, :c, gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), :d, :h) ON CONFLICT (tenant_id, clave_origen) DO NOTHING"),
        {"t": tenant_id, "c": clave, "d": desde, "h": hasta},
    )


def evaluacion(s, tenant_id: str, commitment_id: str) -> str:
    """Decisión mínima plantada (snapshot vacío) para poder referenciarla."""
    oc(s, tenant_id, commitment_id)
    return str(s.execute(
        text("INSERT INTO modulo1.evaluacion_habilitacion (tenant_id, commitment_id, veredicto_de_cumplimiento, resultado_de_decision, "
             "por_sujeto, snapshot) VALUES (:t, :c, 'no_habilitado', 'no_puede_asignarse', '[]', '{}') RETURNING referencia_evaluacion"),
        {"t": tenant_id, "c": commitment_id},
    ).scalar())


def supervisor_de(s, tenant, sujeto_id: str, desde: date = date(2026, 1, 1), supervisor_usuario_id: str | None = None) -> None:
    """Pone al sujeto en el universo del supervisor del tenant de prueba (M-03: quien cambia
    la custodia tiene que administrar al custodio)."""
    s.execute(
        text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
             "VALUES (:t, :s, :u, :d, 'test')"),
        {"t": tenant.tenant_id, "s": sujeto_id, "u": supervisor_usuario_id or tenant.usuarios["supervisor"], "d": desde},
    )
