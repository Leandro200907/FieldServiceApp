"""Ventana temporal única del backlog documental (D23): desde hoy hasta hoy + N días.

N = `configuracion_alertas.horizonte_backlog_dias` (60 por defecto). Usado por Radar,
Backlog, Acciones pendientes y ficha / Mi legajo.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

HORIZONTE_BACKLOG_DIAS_DEFAULT = 60


def horizonte_backlog_dias(session: Session, tenant_id: str) -> int:
    fila = session.execute(
        text("SELECT horizonte_backlog_dias FROM modulo1.configuracion_alertas WHERE tenant_id = :t"),
        {"t": tenant_id},
    ).first()
    if fila is None or fila[0] is None:
        return HORIZONTE_BACKLOG_DIAS_DEFAULT
    return int(fila[0])


def rango_backlog_documental(
    session: Session,
    tenant_id: str,
    hoy: date,
    *,
    vigencia_desde: date | None = None,
    vigencia_hasta: date | None = None,
) -> tuple[date, date]:
    """Período inclusivo de consulta de OC en el backlog (filtro de vigencia de la OC)."""
    desde = vigencia_desde or hoy
    horizonte = horizonte_backlog_dias(session, tenant_id)
    hasta = vigencia_hasta or (hoy + timedelta(days=horizonte))
    return desde, hasta
