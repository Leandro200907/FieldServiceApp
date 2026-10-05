"""E-91: horizonte backlog único y agregación de requisitos exigidos."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.auth.identidad import Identidad, Rol
from app.comun.reloj import hoy_del_tenant
from app.core.ventana_backlog import HORIZONTE_BACKLOG_DIAS_DEFAULT, horizonte_backlog_dias, rango_backlog_documental
from app.db import tenant_session
from app.modules.consultas.requisitos_exigidos_legajo import agregar_requisitos_exigidos, resumen_exigidos_backlog
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_catalogos_maestros,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
)

pytest_plugins = ("tests.test_orquestacion",)


def test_rango_backlog_usa_configuracion_tenant(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    with tenant_session(t.tenant_id) as s:
        assert horizonte_backlog_dias(s, t.tenant_id) == HORIZONTE_BACKLOG_DIAS_DEFAULT
        s.execute(
            text(
                "INSERT INTO modulo1.configuracion_alertas (tenant_id, plazo_aviso_dias, escalamiento_dias, "
                "rol_escalamiento, reconocimiento_dias, horizonte_backlog_dias) "
                "VALUES (:t, 30, 7, 'responsable_legajos', 3, 45) "
                "ON CONFLICT (tenant_id) DO UPDATE SET horizonte_backlog_dias = 45"
            ),
            {"t": t.tenant_id},
        )
        assert horizonte_backlog_dias(s, t.tenant_id) == 45
        desde, hasta = rango_backlog_documental(s, t.tenant_id, hoy)
        assert desde == hoy
        assert hasta == hoy + timedelta(days=45)


def test_agregar_exigidos_incluye_faltante_y_cargado(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    persona = "persona-e91-exig"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    req_a = insertar_definicion(sesion, t.tenant_id, "Req A E91", "persona")
    req_b = insertar_definicion(sesion, t.tenant_id, "Req B E91", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_a: "bloqueante_duro", req_b: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, persona, req_a, hoy, hoy + timedelta(days=365))
    insertar_oc(sesion, t.tenant_id, "OC-E91-EX", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()
    ident = Identidad(t.tenant_id, t.usuarios["responsable_legajos"], frozenset({Rol.RESPONSABLE_LEGAJOS}), None)
    with tenant_session(t.tenant_id) as s:
        mapa = agregar_requisitos_exigidos(s, ident, persona)
        assert set(mapa) == {req_a, req_b}
        assert not mapa[req_a].sin_cobertura
        assert mapa[req_b].sin_cobertura
        res = resumen_exigidos_backlog(mapa, hoy, 30)
        assert res["exigidos"] == 2
        assert res["en_regla_exigidos"] == 1
        assert res["sin_documento"] == 1
        assert res["exigidos_sin_documento"] == 1
