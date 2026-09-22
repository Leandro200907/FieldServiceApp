"""Auditoría externa: `recursos_bajo_custodia` (y su eco en `_SQL_UNIVERSO` y en la
consulta inline de `mi_legajo`) filtraban un período de custodia solo por
`estado = 'vigente'`, sin comparar `desde` contra "hoy". `cambiar_custodia` no valida
`desde` contra el reloj (permite planificar), así que un período con `desde` futuro ya
quedaba "vigente" en la base y aparecía en alcance/legajo ANTES de empezar."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.auth.alcance import alcance_de_sujetos, recursos_bajo_custodia, universo_del_supervisor
from app.comun.reloj import hoy_del_tenant
from app.db import tenant_session
from app.modules.operacion import servicio as op
from tests import apoyo
from tests.test_robustez import _ident

VEH, PER = "vehiculo_FUT", "persona_FUT"


@pytest.fixture
def esc(tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        hoy = hoy_del_tenant(s, t.tenant_id)
        apoyo.legajo(s, t.tenant_id, VEH, "vehiculo")
        apoyo.legajo(s, t.tenant_id, PER, "persona")
        apoyo.supervisor_de(s, t, PER)
        op.cambiar_custodia(
            s, _ident(t, "responsable_legajos"),
            recurso_id=VEH, tipo_recurso="vehiculo", custodio_id=PER, desde=hoy + timedelta(days=1),
        )
    return t, hoy


def test_recursos_bajo_custodia_no_incluye_periodo_que_todavia_no_empezo(esc):
    t, hoy = esc
    with tenant_session(t.tenant_id) as s:
        assert recursos_bajo_custodia(s, PER, hoy) == []
        assert recursos_bajo_custodia(s, PER, hoy + timedelta(days=1)) == [VEH]


def test_universo_del_supervisor_no_incluye_custodia_que_todavia_no_empezo(esc):
    t, hoy = esc
    ident = _ident(t, "supervisor")
    with tenant_session(t.tenant_id) as s:
        assert PER in universo_del_supervisor(s, ident, hoy) and VEH not in universo_del_supervisor(s, ident, hoy)
        assert VEH in universo_del_supervisor(s, ident, hoy + timedelta(days=1))


def test_alcance_de_sujetos_del_tecnico_no_incluye_custodia_que_todavia_no_empezo(esc):
    from app.auth.identidad import Identidad, Rol

    t, hoy = esc
    ident = Identidad(t.tenant_id, t.usuarios["tecnico"], frozenset({Rol.TECNICO}), PER)
    with tenant_session(t.tenant_id) as s:
        assert VEH not in alcance_de_sujetos(s, ident, hoy)
        assert VEH in alcance_de_sujetos(s, ident, hoy + timedelta(days=1))


def test_mi_legajo_no_muestra_recurso_con_custodia_que_todavia_no_empezo(cliente_api, esc):
    t, hoy = esc
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.usuario SET sujeto_id = :sj WHERE tenant_id = :t AND usuario_id = :u"),
                  {"sj": PER, "t": t.tenant_id, "u": t.usuarios["tecnico"]})
    r = cliente_api.get("/v1/consultas/mi_legajo", headers=t.headers("tecnico"))
    assert r.status_code == 200, r.text
    assert r.json()["recursos_bajo_custodia"] == []
