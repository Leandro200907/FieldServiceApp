"""M-03: validaciones y autorización de custodia (cambiar_custodia / corregir_custodia).

FKs (0011): custodia_recurso (tenant, recurso_id) → legajo; periodo_custodia (tenant,
custodio_id) → legajo; periodo_custodia (tenant, custodia_id) → custodia_recurso, sin
CASCADE. Antes de tocar la custodia el servicio valida: recurso existente, activo y del
tipo declarado (vehículo/equipo); custodio existente, activo, persona, dentro del
universo del supervisor; vacío solo para equipo; nunca dos vigentes (ancla FOR UPDATE
sobre el legajo del recurso + índice parcial)."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado, Prohibido
from app.db import tenant_session
from app.modules.operacion import servicio as op
from tests import apoyo
from tests.test_robustez import _en_paralelo, _ident

VEH, EQ, PER, PER2, EMP = "vehiculo_M03", "equipo_M03", "persona_M03", "persona_M03b", "empresa_M03"


@pytest.fixture
def esc(tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        for sid, tipo in ((VEH, "vehiculo"), (EQ, "equipo"), (PER, "persona"), (PER2, "persona"), (EMP, "empresa"),
                          ("persona_fuera", "persona"), ("persona_baja", "persona"), ("vehiculo_baja", "vehiculo")):
            apoyo.legajo(s, t.tenant_id, sid, tipo)
        for sid in (PER, PER2, "persona_baja"):
            apoyo.supervisor_de(s, t, sid)
        s.execute(text("UPDATE modulo1.legajo SET dado_de_baja_en = now() WHERE tenant_id = :t AND sujeto_id IN ('persona_baja', 'vehiculo_baja')"),
                  {"t": t.tenant_id})
    return t


def _cambiar(t, recurso=VEH, tipo="vehiculo", custodio=PER, desde=date(2026, 9, 1), rol="supervisor"):
    def fn():
        with tenant_session(t.tenant_id) as s:
            return op.cambiar_custodia(s, _ident(t, rol), recurso_id=recurso, tipo_recurso=tipo, custodio_id=custodio, desde=desde)
    return fn


def _periodos(t, custodia_id):
    with tenant_session(t.tenant_id) as s:
        return [dict(f) for f in s.execute(text("SELECT periodo_id, custodio_id, desde, hasta, estado, corregido_por "
                                                "FROM modulo1.periodo_custodia WHERE custodia_id = :c ORDER BY creado_en"),
                                           {"c": custodia_id}).mappings()]


# --------------------------------------------------------------------------- validaciones


def test_recurso_inexistente_404(esc):
    with pytest.raises(NoEncontrado):
        _cambiar(esc, recurso="vehiculo_no_existe")()


def test_custodio_inexistente_404(esc):
    with pytest.raises(NoEncontrado) as info:
        _cambiar(esc, custodio="persona_no_existe")()
    assert info.value.detalles == {"custodio_id": "persona_no_existe"}


def test_ids_de_otro_tenant_no_existen(dos_tenants):
    ta, tb = dos_tenants
    with tenant_session(ta.tenant_id) as s:
        apoyo.legajo(s, ta.tenant_id, VEH, "vehiculo")
        apoyo.legajo(s, ta.tenant_id, PER, "persona")
        apoyo.supervisor_de(s, ta, PER)
    with tenant_session(tb.tenant_id) as s:
        apoyo.legajo(s, tb.tenant_id, "vehiculo_B", "vehiculo")
        apoyo.legajo(s, tb.tenant_id, "persona_B", "persona")
        apoyo.supervisor_de(s, tb, "persona_B")
    # El supervisor de B no ve el recurso de A ni al custodio de A: 404, no cruce.
    with pytest.raises(NoEncontrado):
        _cambiar(tb, recurso=VEH, custodio="persona_B")()
    with pytest.raises(NoEncontrado):
        _cambiar(tb, recurso="vehiculo_B", custodio=PER)()
    assert _cambiar(tb, recurso="vehiculo_B", custodio="persona_B")()["periodo_cerrado_id"] is None
    with tenant_session(ta.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.custodia_recurso")).scalar() == 0


@pytest.mark.parametrize("recurso, tipo_declarado", [(PER, "vehiculo"), (EMP, "equipo"), (VEH, "equipo"), (EQ, "vehiculo")])
def test_recurso_persona_o_empresa_o_tipo_distinto_al_declarado_422(esc, recurso, tipo_declarado):
    with pytest.raises(ErrorDeDominio) as info:
        _cambiar(esc, recurso=recurso, tipo=tipo_declarado)()
    assert info.value.codigo == "recurso_no_custodiable" and info.value.status == 422


def test_tipo_recurso_fuera_de_catalogo_422(esc):
    with pytest.raises(ErrorDeDominio) as info:
        _cambiar(esc, recurso=PER, tipo="persona")()
    assert info.value.codigo == "regla_de_dominio"


@pytest.mark.parametrize("custodio", [VEH, EQ, EMP])
def test_custodio_que_no_es_persona_422(esc, custodio):
    with pytest.raises(ErrorDeDominio) as info:
        _cambiar(esc, custodio=custodio)()
    assert info.value.codigo == "custodio_no_permitido"


def test_sin_custodio_solo_para_equipo(esc):
    with pytest.raises(ErrorDeDominio) as info:
        _cambiar(esc, recurso=VEH, tipo="vehiculo", custodio=None)()
    assert info.value.codigo == "custodio_requerido"
    r = _cambiar(esc, recurso=EQ, tipo="equipo", custodio=None)()
    assert _periodos(esc, r["custodia_id"])[0]["custodio_id"] is None


def test_legajo_dado_de_baja_422(esc):
    with pytest.raises(ErrorDeDominio) as info:
        _cambiar(esc, recurso="vehiculo_baja")()
    assert info.value.codigo == "legajo_dado_de_baja"
    with pytest.raises(ErrorDeDominio) as info:
        _cambiar(esc, custodio="persona_baja")()
    assert info.value.codigo == "legajo_dado_de_baja"


def test_supervisor_fuera_de_alcance_403(esc):
    with pytest.raises(Prohibido):
        _cambiar(esc, custodio="persona_fuera")()
    # Otro supervisor del mismo tenant que no administra a la persona: 403 también.
    with tenant_session(esc.tenant_id) as s:
        otro = str(uuid.uuid4())
        s.execute(text("INSERT INTO modulo1.usuario (tenant_id, usuario_id, email, nombre, password_hash, roles) VALUES (:t, :u, :e, 'otro', 'x', '{supervisor}')"),
                  {"t": esc.tenant_id, "u": otro, "e": f"{otro}@t.test"})
    from app.auth.identidad import Identidad, Rol
    with tenant_session(esc.tenant_id) as s, pytest.raises(Prohibido):
        op.cambiar_custodia(s, Identidad(esc.tenant_id, otro, frozenset({Rol.SUPERVISOR})),
                            recurso_id=VEH, tipo_recurso="vehiculo", custodio_id=PER, desde=date(2026, 9, 1))


def test_solo_supervisor_por_matriz_de_roles(esc):
    """Matriz 2.2 de no-funcionales: CambiarCustodia es del Supervisor. El responsable de
    legajos NO opera la custodia aunque tenga todo el tenant en lectura."""
    with pytest.raises(Prohibido):
        _cambiar(esc, rol="responsable_legajos")()


def test_corregir_valida_el_custodio_nuevo(esc):
    r = _cambiar(esc)()
    for custodio, codigo in ((VEH, "custodio_no_permitido"), ("persona_baja", "legajo_dado_de_baja")):
        with tenant_session(esc.tenant_id) as s, pytest.raises(ErrorDeDominio) as info:
            op.corregir_custodia(s, _ident(esc, "supervisor"), periodo_id=r["periodo_id"], custodio_id=custodio)
        assert info.value.codigo == codigo
    with tenant_session(esc.tenant_id) as s, pytest.raises(Prohibido):
        op.corregir_custodia(s, _ident(esc, "supervisor"), periodo_id=r["periodo_id"], custodio_id="persona_fuera")
    with tenant_session(esc.tenant_id) as s, pytest.raises(NoEncontrado):
        op.corregir_custodia(s, _ident(esc, "supervisor"), periodo_id=r["periodo_id"], custodio_id="nadie")


# --------------------------------------------------------------------------- concurrencia e historia


def test_dos_primeras_custodias_concurrentes_del_mismo_recurso_queda_una_vigente(esc):
    salidas = _en_paralelo([_cambiar(esc, custodio=PER, desde=date(2026, 9, 1)), _cambiar(esc, custodio=PER2, desde=date(2026, 9, 1))])
    ok = [r for r, e in salidas if e is None]
    errores = [e for _, e in salidas if e is not None]
    # Serializadas por el ancla (legajo del recurso): la segunda ve el vigente con el mismo
    # `desde` y cae en la regla de dominio, no en el índice.
    assert len(ok) == 1 and len(errores) == 1 and isinstance(errores[0], Conflicto), salidas
    with tenant_session(esc.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.custodia_recurso WHERE recurso_id = :r"), {"r": VEH}).scalar() == 1
    periodos = _periodos(esc, ok[0]["custodia_id"])
    assert [p["estado"] for p in periodos] == ["vigente"]


def test_dos_concurrentes_con_fechas_distintas_encadenan_sin_dos_vigentes(esc):
    salidas = _en_paralelo([_cambiar(esc, custodio=PER, desde=date(2026, 9, 1)), _cambiar(esc, custodio=PER2, desde=date(2026, 9, 10))])
    ok = [r for r, e in salidas if e is None]
    custodia_id = ok[0]["custodia_id"]
    periodos = _periodos(esc, custodia_id)
    assert len([p for p in periodos if p["estado"] == "vigente"]) == 1
    # O bien se serializaron en orden (2 períodos: cerrado + vigente), o bien la de fecha
    # posterior entró primero y la de fecha anterior fue rechazada (1 vigente, 1 Conflicto).
    if len(ok) == 2:
        assert sorted(p["estado"] for p in periodos) == ["cerrado", "vigente"]
        assert next(p for p in periodos if p["estado"] == "cerrado")["hasta"] == date(2026, 9, 9)
    else:
        assert isinstance(next(e for _, e in salidas if e), Conflicto) and len(periodos) == 1


def test_cambio_valido_conserva_historia_y_correccion_no_borra(esc):
    r1 = _cambiar(esc, custodio=PER, desde=date(2026, 9, 1))()
    r2 = _cambiar(esc, custodio=PER2, desde=date(2026, 9, 10))()
    assert r2["periodo_cerrado_id"] == r1["periodo_id"]
    with tenant_session(esc.tenant_id) as s:
        r3 = op.corregir_custodia(s, _ident(esc, "supervisor"), periodo_id=r2["periodo_id"], custodio_id=PER, motivo="tipeo")
    periodos = {str(p["periodo_id"]): p for p in _periodos(esc, r1["custodia_id"])}
    assert len(periodos) == 3
    assert periodos[r1["periodo_id"]]["estado"] == "cerrado" and periodos[r1["periodo_id"]]["hasta"] == date(2026, 9, 9)
    assert periodos[r2["periodo_id"]]["estado"] == "corregido" and str(periodos[r2["periodo_id"]]["corregido_por"]) == r3["periodo_id"]
    assert periodos[r3["periodo_id"]]["estado"] == "vigente" and periodos[r3["periodo_id"]]["custodio_id"] == PER
    with tenant_session(esc.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.periodo_custodia WHERE custodia_id = :c AND estado = 'vigente'"),
                         {"c": r1["custodia_id"]}).scalar() == 1


def test_borrar_custodia_no_arrastra_periodos(esc):
    """FK periodo→custodia sin CASCADE (0011): el historial bloquea el borrado del agregado."""
    import psycopg
    from sqlalchemy.exc import IntegrityError
    r = _cambiar(esc)()
    with tenant_session(esc.tenant_id) as s:
        with pytest.raises(IntegrityError) as info:
            s.execute(text("DELETE FROM modulo1.custodia_recurso WHERE custodia_id = :c"), {"c": r["custodia_id"]})
        assert isinstance(info.value.orig, psycopg.errors.ForeignKeyViolation)
        assert info.value.orig.diag.constraint_name == "fk_periodo_custodia__custodia_id"
        s.rollback()
