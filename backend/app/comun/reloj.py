"""Reloj inyectable (8.6): nunca `date.today()` ni `datetime.now()` sueltos en dominio.

`ahora_utc()` devuelve un instante aware en UTC. `hoy_del_tenant()` lo convierte a la
fecha civil del tenant — la ÚNICA forma válida de obtener "hoy" para comparar vigencias
(0.3 de especificacion.md, caso de oro 6.4).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def zona_horaria_del_tenant(session: Session, tenant_id: str) -> str:
    fila = session.execute(
        text("SELECT zona_horaria FROM modulo1.tenant WHERE tenant_id = :t"), {"t": tenant_id}
    ).first()
    return fila[0] if fila and fila[0] else settings.tenant_default_timezone


def hoy_del_tenant(session: Session, tenant_id: str, ahora: datetime | None = None) -> date:
    instante = ahora or ahora_utc()
    if instante.tzinfo is None:
        raise ValueError("ahora debe ser timezone-aware (UTC)")
    return instante.astimezone(ZoneInfo(zona_horaria_del_tenant(session, tenant_id))).date()
