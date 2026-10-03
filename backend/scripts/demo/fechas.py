"""Fechas relativas al hoy del tenant (America/Argentina/Buenos_Aires)."""
from __future__ import annotations

from datetime import date, timedelta

from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.db import tenant_session


def hoy_tenant(tenant_id: str) -> date:
    with tenant_session(tenant_id) as s:
        return hoy_del_tenant(s, tenant_id, ahora_utc())


def rango_vigente(hoy: date) -> tuple[date, date]:
    return hoy - timedelta(days=200), hoy + timedelta(days=120)


def rango_por_vencer(hoy: date) -> tuple[date, date]:
    return hoy - timedelta(days=60), hoy + timedelta(days=20)


def rango_vencido(hoy: date) -> tuple[date, date]:
    return hoy - timedelta(days=400), hoy - timedelta(days=15)


def rango_oc_terminada(hoy: date) -> tuple[date, date]:
    return hoy - timedelta(days=90), hoy - timedelta(days=10)


def rango_oc_en_curso(hoy: date) -> tuple[date, date]:
    return hoy - timedelta(days=5), hoy + timedelta(days=30)


def rango_oc_futura(hoy: date) -> tuple[date, date]:
    return hoy + timedelta(days=14), hoy + timedelta(days=45)
