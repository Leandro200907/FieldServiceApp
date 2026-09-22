"""Auditoría externa (informe AUDITORIA_DB400E6, hallazgo A-01): `cambiar_custodia`
cierra el período anterior (`estado='cerrado'`) en el mismo instante en que programa una
transferencia futura, aunque el nuevo período todavía no haya empezado. Como las consultas
de alcance sólo miraban `estado='vigente'`, el custodio ACTUAL perdía acceso al recurso
desde el momento en que se programaba la transferencia, no desde que efectivamente
arrancaba — y el futuro custodio tampoco lo veía todavía. Reproducción: persona A custodia
desde 2026-01-01; se programa transferencia a B para dentro de 10 días. Hoy, A tiene que
conservar el recurso y B no tiene que verlo todavía."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.auth.alcance import periodo_custodia_efectivo, recursos_bajo_custodia
from app.comun.reloj import hoy_del_tenant
from app.db import tenant_session
from app.modules.alertas.servicio import _persona_responsable
from app.modules.operacion import servicio as op
from tests import apoyo
from tests.test_robustez import _ident

VEH, A, B = "vehiculo_TRANSF", "persona_TRANSF_A", "persona_TRANSF_B"


@pytest.fixture
def esc(tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        hoy = hoy_del_tenant(s, t.tenant_id)
        apoyo.legajo(s, t.tenant_id, VEH, "vehiculo")
        apoyo.legajo(s, t.tenant_id, A, "persona")
        apoyo.legajo(s, t.tenant_id, B, "persona")
        apoyo.supervisor_de(s, t, A)
        apoyo.supervisor_de(s, t, B)
        # A ya tiene el vehículo desde antes de hoy.
        op.cambiar_custodia(s, _ident(t, "responsable_legajos"), recurso_id=VEH, tipo_recurso="vehiculo",
                             custodio_id=A, desde=hoy - timedelta(days=30))
        # Se programa la transferencia a B para dentro de 10 días — todavía no arrancó.
        op.cambiar_custodia(s, _ident(t, "responsable_legajos"), recurso_id=VEH, tipo_recurso="vehiculo",
                             custodio_id=B, desde=hoy + timedelta(days=10))
    return t, hoy


def test_custodio_actual_conserva_el_recurso_hasta_que_arranca_la_transferencia(esc):
    t, hoy = esc
    with tenant_session(t.tenant_id) as s:
        assert recursos_bajo_custodia(s, A, hoy) == [VEH]
        assert recursos_bajo_custodia(s, B, hoy) == []
        # El día que arranca la transferencia, se invierte.
        futuro = hoy + timedelta(days=10)
        assert recursos_bajo_custodia(s, A, futuro) == []
        assert recursos_bajo_custodia(s, B, futuro) == [VEH]


def test_periodo_custodia_efectivo_hoy_es_el_de_a_no_el_de_b(esc):
    t, hoy = esc
    with tenant_session(t.tenant_id) as s:
        periodo = periodo_custodia_efectivo(s, t.tenant_id, VEH, hoy)
        assert periodo is not None and periodo["custodio_id"] == A


def test_alerta_de_vencimiento_del_vehiculo_sigue_notificando_al_custodio_actual(esc):
    t, hoy = esc
    with tenant_session(t.tenant_id) as s:
        assert _persona_responsable(s, t.tenant_id, VEH, "vehiculo", hoy) == A


def test_mi_legajo_de_a_sigue_mostrando_el_vehiculo(cliente_api, esc):
    t, hoy = esc
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.usuario SET sujeto_id = :sj WHERE tenant_id = :t AND usuario_id = :u"),
                  {"sj": A, "t": t.tenant_id, "u": t.usuarios["tecnico"]})
    r = cliente_api.get("/v1/consultas/mi_legajo", headers=t.headers("tecnico"))
    assert r.status_code == 200, r.text
    assert [c["legajo"]["sujeto_id"] for c in r.json()["recursos_bajo_custodia"]] == [VEH]
