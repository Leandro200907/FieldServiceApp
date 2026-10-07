"""Matriz vigente por clave (cliente, locación, tipo de servicio) en una fecha."""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


def tiene_matriz_vigente(
    session: Session,
    tenant_id: str,
    cliente_id: str,
    locacion_id: str,
    tipo_servicio_id: str,
    hoy: date,
) -> bool:
    """True si existe al menos una versión de matriz vigente en `hoy` (misma regla que aviso OC sin matriz)."""
    return bool(
        session.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM modulo1.matriz_requisitos m "
                "WHERE m.tenant_id = :t AND m.cliente_id = :c AND m.locacion_id = :l AND m.tipo_servicio_id = :ts "
                "AND m.vigente_desde <= :hoy AND (m.vigente_hasta IS NULL OR m.vigente_hasta >= :hoy))"
            ),
            {"t": tenant_id, "c": cliente_id, "l": locacion_id, "ts": tipo_servicio_id, "hoy": hoy},
        ).scalar()
    )
