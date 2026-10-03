"""B-6: aviso de incumplimiento también sin documento verificado vigente."""
from __future__ import annotations

from sqlalchemy import text

from app.comun.reloj import hoy_del_tenant
from app.core.incumplimiento_empresa import registrar_vencimientos_de_empresa
from tests.test_a07_revaluacion import _base, insertar_definicion
from tests.test_orquestacion import sesion  # noqa: F401


def test_incumplimiento_por_ausencia_de_documento_verificado(tenant_de_prueba, sesion):
    t = tenant_de_prueba
    _base(sesion, t)
    req_extra = insertar_definicion(sesion, t.tenant_id, "Poliza extra", "empresa")
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    sesion.execute(text("DELETE FROM modulo1.documento WHERE requisito_definicion_id = :r"), {"r": req_extra})
    r = registrar_vencimientos_de_empresa(sesion, t.tenant_id, hoy)
    assert r["causas_nuevas"] >= 1
    activas = sesion.execute(text(
        "SELECT requisito_definicion_id::text FROM modulo1.aviso_incumplimiento_empresa_causa "
        "WHERE tenant_id = :t AND estado = 'activa'"
    ), {"t": t.tenant_id}).scalars().all()
    assert req_extra in activas
