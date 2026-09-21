"""M-02 (0012): unicidad de excepciones y constancias ACTIVAS.

Claves de negocio:
- excepción `otorgada`: (tenant, sujeto, requisito, commitment)                → uq_excepcion_activa
- constancia `vigente` general (commitment NULL): (tenant, sujeto, requisito, cliente) → uq_constancia_general_activa
- constancia `vigente` específica: (tenant, sujeto, requisito, cliente, commitment) → uq_constancia_especifica_activa

Los servicios bloquean el legajo del sujeto (ancla) y cierran/reemplazan la anterior
antes de insertar; una colisión residual se traduce a 409 de dominio estable."""
from __future__ import annotations

from datetime import date

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.errores import Conflicto
from app.db import tenant_session
from app.modules.operacion import servicio as op
from tests.test_orquestacion import armar_escenario, insertar_oc
from tests.test_robustez import _en_paralelo, _ident

PERSONA = "persona_0042"
EMPRESA = "empresa_0001"


@pytest.fixture
def esc(tenant_de_prueba):
    """Escenario: persona con requisito excepcionable, empresa con requisito bloqueante_duro,
    OC-1, supervisor con la persona en su universo y una decisión hecha por el responsable."""
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        e = armar_escenario(s, t.tenant_id, clasificacion_persona="excepcionable")
        insertar_oc(s, t.tenant_id, "OC-1", e["clave"], date(2026, 10, 1), date(2026, 10, 5))
        s.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                       "VALUES (:t, :p, :u, '2026-01-01', 'test')"), {"t": t.tenant_id, "p": PERSONA, "u": t.usuarios["supervisor"]})
    with tenant_session(t.tenant_id) as s:
        dec = op.evaluar_habilitacion(s, _ident(t, "responsable_legajos"), commitment_id="OC-1", sujetos_propuestos=[PERSONA])
    return {**e, "t": t, "referencia": dec["referencia_evaluacion"]}


def _otorgar(esc, motivo="m"):
    t = esc["t"]

    def fn():
        with tenant_session(t.tenant_id) as s:
            return op.otorgar_excepcion(
                s, _ident(t, "supervisor"), referencia_evaluacion=esc["referencia"], sujeto_id=PERSONA,
                requisito_definicion_id=esc["req_apto"], commitment_id="OC-1", motivo=motivo,
            )
    return fn


def _constancia(esc, commitment_id=None, evidencia="mail"):
    t = esc["t"]

    def fn():
        with tenant_session(t.tenant_id) as s:
            return op.registrar_constancia_del_cliente(
                s, _ident(t, "responsable_legajos"), sujeto_id=EMPRESA, requisito_definicion_id=esc["req_empresa"],
                cliente_id=esc["cliente_id"], evidencia=evidencia, commitment_id=commitment_id,
            )
    return fn


def _filas(t, tabla, id_col):
    with tenant_session(t.tenant_id) as s:
        return [dict(f) for f in s.execute(text(f"SELECT {id_col} AS id, estado, * FROM modulo1.{tabla} WHERE tenant_id = :t ORDER BY creado_en"),
                                           {"t": t.tenant_id}).mappings()]


# --------------------------------------------------------------------------- concurrencia


def test_dos_primeras_excepciones_simultaneas_queda_una_activa(esc):
    salidas = _en_paralelo([_otorgar(esc, "a"), _otorgar(esc, "b")])
    ok = [r for r, e in salidas if e is None]
    errores = [e for _, e in salidas if e is not None]
    assert len(ok) == 1 and len(errores) == 1, salidas
    assert isinstance(errores[0], Conflicto) and errores[0].status == 409
    filas = _filas(esc["t"], "excepcion", "excepcion_id")
    assert [f["estado"] for f in filas] == ["otorgada"]


def test_dos_primeras_constancias_generales_simultaneas_queda_una_vigente(esc):
    salidas = _en_paralelo([_constancia(esc, evidencia="a"), _constancia(esc, evidencia="b")])
    assert all(e is None for _, e in salidas), salidas
    filas = _filas(esc["t"], "constancia_cliente", "constancia_id")
    vigentes = [f for f in filas if f["estado"] == "vigente"]
    assert len(filas) == 2 and len(vigentes) == 1
    # La segunda serializada reemplazó a la primera: historial coherente, no una carrera.
    reemplazada = next(f for f in filas if f["estado"] == "reemplazada")
    assert str(reemplazada["reemplazada_por"]) == str(vigentes[0]["id"])
    assert {r["constancia_reemplazada_id"] for r, _ in salidas} == {None, str(reemplazada["id"])}


def test_dos_primeras_constancias_especificas_simultaneas_queda_una_vigente(esc):
    salidas = _en_paralelo([_constancia(esc, "OC-1", "a"), _constancia(esc, "OC-1", "b")])
    assert all(e is None for _, e in salidas), salidas
    filas = _filas(esc["t"], "constancia_cliente", "constancia_id")
    assert sorted(f["estado"] for f in filas) == ["reemplazada", "vigente"]
    assert all(f["commitment_id"] == "OC-1" for f in filas)


# --------------------------------------------------------------------------- reemplazo e historial


def test_reemplazo_correcto_no_viola_el_indice_y_general_y_especifica_conviven(esc):
    g1 = _constancia(esc)()
    g2 = _constancia(esc, evidencia="v2")()
    e1 = _constancia(esc, "OC-1")()
    e2 = _constancia(esc, "OC-1", "v2")()
    assert g2["constancia_reemplazada_id"] == g1["constancia_id"]
    assert e1["constancia_reemplazada_id"] is None            # la general NO se confunde con la específica
    assert e2["constancia_reemplazada_id"] == e1["constancia_id"]
    filas = {str(f["id"]): f for f in _filas(esc["t"], "constancia_cliente", "constancia_id")}
    assert filas[g1["constancia_id"]]["estado"] == "reemplazada" and str(filas[g1["constancia_id"]]["reemplazada_por"]) == g2["constancia_id"]
    assert filas[e1["constancia_id"]]["estado"] == "reemplazada" and str(filas[e1["constancia_id"]]["reemplazada_por"]) == e2["constancia_id"]
    assert sorted(str(k) for k, f in filas.items() if f["estado"] == "vigente") == sorted([g2["constancia_id"], e2["constancia_id"]])


def test_varias_filas_historicas_de_excepcion_y_constancia_conviven(esc):
    t = esc["t"]
    ids = []
    for i in range(3):
        r = _otorgar(esc, f"ronda {i}")()
        ids.append(r["excepcion_id"])
        with pytest.raises(Conflicto):           # segunda activa: 409 antes de tocar la base
            _otorgar(esc)()
        with tenant_session(t.tenant_id) as s:
            op.revocar_excepcion(s, _ident(t, "supervisor"), excepcion_id=r["excepcion_id"])
    final = _otorgar(esc, "final")()
    filas = _filas(t, "excepcion", "excepcion_id")
    assert sorted(f["estado"] for f in filas) == ["otorgada", "revocada", "revocada", "revocada"]
    assert str(next(f for f in filas if f["estado"] == "otorgada")["id"]) == final["excepcion_id"]

    for i in range(4):
        _constancia(esc, evidencia=f"g{i}")()
    filas = _filas(t, "constancia_cliente", "constancia_id")
    assert sorted(f["estado"] for f in filas) == ["reemplazada"] * 3 + ["vigente"]


# --------------------------------------------------------------------------- colisión residual → 409 estable


class _SesionSinChequeo:
    """Proxy que hace que la consulta previa ('ya'/'anterior') no vea nada: simula la
    ventana residual en la que dos transacciones pasaron el chequeo. Todo lo demás va a la
    sesión real, así el INSERT choca contra el índice parcial."""

    def __init__(self, real, marca):
        self._real, self._marca = real, marca

    def execute(self, stmt, *a, **k):
        if self._marca in str(stmt):
            class _Vacio:
                def first(self): return None
                def mappings(self): return self
            return _Vacio()
        return self._real.execute(stmt, *a, **k)

    def __getattr__(self, n):
        return getattr(self._real, n)


def test_colision_residual_de_excepcion_es_409_de_dominio(esc):
    t = esc["t"]
    _otorgar(esc)()
    with tenant_session(t.tenant_id) as s:
        with pytest.raises(Conflicto) as info:
            op.otorgar_excepcion(
                _SesionSinChequeo(s, "SELECT excepcion_id FROM modulo1.excepcion"), _ident(t, "supervisor"),
                referencia_evaluacion=esc["referencia"], sujeto_id=PERSONA, requisito_definicion_id=esc["req_apto"],
                commitment_id="OC-1", motivo="x",
            )
        assert info.value.status == 409 and info.value.codigo == "excepcion_activa_duplicada"
        assert isinstance(info.value.__cause__, IntegrityError)
        s.rollback()


@pytest.mark.parametrize("commitment_id, indice", [(None, "uq_constancia_general_activa"), ("OC-1", "uq_constancia_especifica_activa")])
def test_colision_residual_de_constancia_es_409_de_dominio(esc, commitment_id, indice):
    t = esc["t"]
    _constancia(esc, commitment_id)()
    with tenant_session(t.tenant_id) as s:
        with pytest.raises(Conflicto) as info:
            op.registrar_constancia_del_cliente(
                _SesionSinChequeo(s, "SELECT constancia_id FROM modulo1.constancia_cliente"), _ident(t, "responsable_legajos"),
                sujeto_id=EMPRESA, requisito_definicion_id=esc["req_empresa"], cliente_id=esc["cliente_id"],
                evidencia="x", commitment_id=commitment_id,
            )
        assert info.value.status == 409 and info.value.codigo == "constancia_activa_duplicada"
        assert info.value.__cause__.orig.diag.constraint_name == indice
        s.rollback()


def test_api_colision_residual_responde_409_no_500(cliente_api, esc, monkeypatch):
    """Por HTTP: el 23505 residual sale como 409 con código de dominio (no 500)."""
    from tests.test_comandos_operacion import _post
    t = esc["t"]
    _otorgar(esc)()
    original = op.otorgar_excepcion

    def sin_chequeo(session, identidad, **kw):
        return original(_SesionSinChequeo(session, "SELECT excepcion_id FROM modulo1.excepcion"), identidad, **kw)
    monkeypatch.setattr(op, "otorgar_excepcion", sin_chequeo)
    r = _post(cliente_api, t, "supervisor", "otorgar_excepcion",
              {"referencia_evaluacion": esc["referencia"], "sujeto_id": PERSONA, "requisito_definicion_id": esc["req_apto"],
               "commitment_id": "OC-1", "motivo": "x"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["codigo"] == "excepcion_activa_duplicada"


# --------------------------------------------------------------------------- la base sola


def test_indices_parciales_rechazan_duplicado_activo_y_permiten_historial(esc):
    t = esc["t"]
    with tenant_session(t.tenant_id) as s:
        for estado in ("revocada", "vencida", "revocada"):
            s.execute(text("INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, "
                           "commitment_id, otorgada_por, motivo, estado) VALUES (:t, :e, :p, :r, 'OC-1', 'u', 'm', :es)"),
                      {"t": t.tenant_id, "e": esc["referencia"], "p": PERSONA, "r": esc["req_apto"], "es": estado})
        s.execute(text("INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, "
                       "commitment_id, otorgada_por, motivo) VALUES (:t, :e, :p, :r, 'OC-1', 'u', 'm')"),
                  {"t": t.tenant_id, "e": esc["referencia"], "p": PERSONA, "r": esc["req_apto"]})
        with pytest.raises(IntegrityError) as info:
            s.execute(text("INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, "
                           "commitment_id, otorgada_por, motivo) VALUES (:t, :e, :p, :r, 'OC-1', 'u', 'm')"),
                      {"t": t.tenant_id, "e": esc["referencia"], "p": PERSONA, "r": esc["req_apto"]})
        assert isinstance(info.value.orig, psycopg.errors.UniqueViolation)
        assert info.value.orig.diag.constraint_name == "uq_excepcion_activa"
        s.rollback()


def test_pg_indexes_definicion_exacta():
    with tenant_session("00000000-0000-0000-0000-000000000000") as s:
        defs = dict(s.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'modulo1' AND indexname LIKE 'uq_%activa'")).all())
    assert defs["uq_excepcion_activa"].endswith("(tenant_id, sujeto_id, requisito_definicion_id, commitment_id) WHERE (estado = 'otorgada'::text)")
    assert defs["uq_constancia_general_activa"].endswith("(tenant_id, sujeto_id, requisito_definicion_id, cliente_id) WHERE ((estado = 'vigente'::text) AND (commitment_id IS NULL))")
    assert defs["uq_constancia_especifica_activa"].endswith("(tenant_id, sujeto_id, requisito_definicion_id, cliente_id, commitment_id) WHERE ((estado = 'vigente'::text) AND (commitment_id IS NOT NULL))")
    assert all(d.startswith("CREATE UNIQUE INDEX") for d in defs.values())
