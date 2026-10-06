"""Reloj inyectable (8.6): nunca `date.today()` ni `datetime.now()` sueltos en dominio.

`ahora_utc()` devuelve un instante aware en UTC. `hoy_del_tenant()` lo convierte a la
fecha civil del tenant — la ÚNICA forma válida de obtener "hoy" para comparar vigencias
(0.3 de especificacion.md, caso de oro 6.4).

En pytest, `conftest` congela el instante vía `ContextVar` (ver `congelar_reloj_utc`).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

_reloj_congelado: ContextVar[datetime | None] = ContextVar("fsm_reloj_congelado", default=None)
# Compartido entre hilos del mismo proceso (tests concurrentes); lo fija `congelar_reloj_utc`.
_reloj_proceso_utc: datetime | None = None


def ahora_utc() -> datetime:
    if _reloj_proceso_utc is not None:
        return _reloj_proceso_utc
    congelado = _reloj_congelado.get()
    if congelado is not None:
        return congelado
    return datetime.now(timezone.utc)


@contextmanager
def congelar_reloj_utc(instante: datetime | None):
    """Congela `ahora_utc()` (y por tanto `hoy_del_tenant` sin parámetro) en el contexto actual."""
    global _reloj_proceso_utc
    token = _reloj_congelado.set(instante)
    prev_proceso = _reloj_proceso_utc
    _reloj_proceso_utc = instante
    try:
        yield
    finally:
        _reloj_proceso_utc = prev_proceso
        _reloj_congelado.reset(token)


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
