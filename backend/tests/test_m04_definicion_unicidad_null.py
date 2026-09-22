"""M-04 (0013): unicidad NULL-aware de la definición de requisito.

Clave de negocio completa: (tenant_id, nombre, categoria, tipo_sujeto_aplicable,
locacion_id) con `UNIQUE NULLS NOT DISTINCT`, así dos definiciones iguales con
locación NULL (todo lo que no es inducción) chocan en la base, no solo en el servicio."""
from __future__ import annotations

import uuid

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.errores import Conflicto
from app.db import tenant_session
from app.modules.requisitos import esquemas as esq
from app.modules.requisitos import servicio as req
from tests.test_robustez import _en_paralelo, _ident

CMD = "/v1/comandos/dar_de_alta_definicion_de_requisito"


def _insertar(s, tenant_id, nombre="Apto médico", categoria="documento", tipo="persona", locacion=None):
    return s.execute(
        text("INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id) "
             "VALUES (:t, :n, :c, :ts, :l) RETURNING requisito_definicion_id"),
        {"t": tenant_id, "n": nombre, "c": categoria, "ts": tipo, "l": locacion},
    ).scalar()


def _alta(t, nombre="Apto médico", categoria="documento", locacion=None):
    def fn():
        with tenant_session(t.tenant_id) as s:
            return req.dar_de_alta_definicion_de_requisito(
                s, _ident(t, "configuracion"),
                esq.DarDeAltaDefinicionDeRequisito(nombre=nombre, categoria=categoria, tipo_sujeto_aplicable="persona", locacion_id=locacion),
            )
    return fn


# --------------------------------------------------------------------------- la base


def test_dos_iguales_con_locacion_null_la_segunda_falla_en_la_base(tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        _insertar(s, t.tenant_id)
        with pytest.raises(IntegrityError) as info:
            _insertar(s, t.tenant_id)
        assert isinstance(info.value.orig, psycopg.errors.UniqueViolation)
        assert info.value.orig.diag.constraint_name == "uq_definicion_clave_negocio"
        s.rollback()


def test_misma_clave_en_distintas_locaciones_se_permite(tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        a = _insertar(s, t.tenant_id, "Inducción HSE", "induccion", locacion=str(uuid.uuid4()))
        b = _insertar(s, t.tenant_id, "Inducción HSE", "induccion", locacion=str(uuid.uuid4()))
        assert a != b
        # Distinta categoría / tipo de sujeto tampoco chocan con la de locación NULL.
        _insertar(s, t.tenant_id, "Apto médico", "documento", "persona")
        _insertar(s, t.tenant_id, "Apto médico", "competencia", "persona")
        _insertar(s, t.tenant_id, "Apto médico", "documento", "vehiculo")
        assert s.execute(text("SELECT count(*) FROM modulo1.definicion_requisito")).scalar() == 5


def test_misma_clave_en_distintos_tenants_se_permite(dos_tenants):
    ta, tb = dos_tenants
    with tenant_session(ta.tenant_id) as s:
        _insertar(s, ta.tenant_id)
    with tenant_session(tb.tenant_id) as s:
        _insertar(s, tb.tenant_id)
        assert s.execute(text("SELECT count(*) FROM modulo1.definicion_requisito")).scalar() == 1


def test_pg_constraint_es_unique_nulls_not_distinct():
    with tenant_session("00000000-0000-0000-0000-000000000000") as s:
        defs = dict(s.execute(text(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'modulo1.definicion_requisito'::regclass AND contype = 'u'")).all())
    assert defs["uq_definicion_clave_negocio"] == "UNIQUE NULLS NOT DISTINCT (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id)"
    assert "uq_definicion_requisito" not in defs


# --------------------------------------------------------------------------- servicio y API


def test_dos_altas_concurrentes_queda_una_y_la_otra_es_409_de_dominio(tenant_de_prueba):
    t = tenant_de_prueba
    salidas = _en_paralelo([_alta(t), _alta(t)])
    ok = [r for r, e in salidas if e is None]
    errores = [e for _, e in salidas if e is not None]
    assert len(ok) == 1 and len(errores) == 1, salidas
    assert isinstance(errores[0], Conflicto) and errores[0].status == 409
    assert errores[0].codigo in ("conflicto", "definicion_duplicada")  # chequeo previo o carrera residual
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.definicion_requisito WHERE nombre = 'Apto médico'")).scalar() == 1


def test_carrera_residual_se_traduce_a_409_definicion_duplicada(tenant_de_prueba):
    """Se simula la ventana entre el chequeo previo y el INSERT: la fila igual aparece
    después del chequeo (otra transacción) y el 23505 sale como 409 de dominio."""
    t = tenant_de_prueba

    class _SinChequeo:
        def __init__(self, real): self._real = real

        def execute(self, stmt, *a, **k):
            if "SELECT requisito_definicion_id, activa FROM modulo1.definicion_requisito" in str(stmt):
                class _Vacio:
                    def mappings(self): return self
                    def first(self): return None
                return _Vacio()
            return self._real.execute(stmt, *a, **k)

        def __getattr__(self, n): return getattr(self._real, n)

    with tenant_session(t.tenant_id) as s:
        _insertar(s, t.tenant_id)
    with tenant_session(t.tenant_id) as s:
        with pytest.raises(Conflicto) as info:
            req.dar_de_alta_definicion_de_requisito(
                _SinChequeo(s), _ident(t, "configuracion"),
                esq.DarDeAltaDefinicionDeRequisito(nombre="Apto médico", categoria="documento", tipo_sujeto_aplicable="persona"),
            )
        assert info.value.status == 409 and info.value.codigo == "definicion_duplicada"
        assert isinstance(info.value.__cause__, IntegrityError)
        s.rollback()


def test_api_repetida_con_locacion_null_responde_409_no_500(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    body = {"nombre": "Apto médico", "categoria": "documento", "tipo_sujeto_aplicable": "persona"}
    assert cliente_api.post(CMD, json=body, headers=t.headers("configuracion")).status_code == 200
    r = cliente_api.post(CMD, json=body, headers=t.headers("configuracion"))
    assert r.status_code == 409 and r.json()["error"]["codigo"] == "conflicto"
    # Dada de baja no libera la clave: sigue siendo 409 (la clave es de todas las filas).
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.definicion_requisito SET activa = false WHERE tenant_id = :t"), {"t": t.tenant_id})
    r = cliente_api.post(CMD, json=body, headers=t.headers("configuracion"))
    assert r.status_code == 409


# --------------------------------------------------------------------------- la migración aborta con duplicados


def test_migracion_0013_aborta_si_hay_duplicados_null_y_no_borra_nada(tenant_de_prueba):
    """Con la base en 0012 (UNIQUE clásico) se plantan dos definiciones iguales con
    locación NULL; `upgrade 0013` debe abortar con diagnóstico, dejar las dos filas y la
    restricción vieja intactas. Limpiadas, el upgrade pasa."""
    import os
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    os.environ.setdefault("ENV_FILE", ".env")
    t = tenant_de_prueba
    command.downgrade(cfg, "0012_unicidad_operacion_activa")
    try:
        with tenant_session(t.tenant_id) as s:
            _insertar(s, t.tenant_id)
            _insertar(s, t.tenant_id)  # con UNIQUE clásico entra (NULL <> NULL)
        with pytest.raises(RuntimeError, match="0013 abortada: 1 clave"):
            command.upgrade(cfg, "head")
        with tenant_session(t.tenant_id) as s:
            assert s.execute(text("SELECT count(*) FROM modulo1.definicion_requisito")).scalar() == 2
            assert s.execute(text("SELECT conname FROM pg_constraint WHERE conname = 'uq_definicion_requisito'")).scalar() == "uq_definicion_requisito"
    finally:
        with tenant_session(t.tenant_id) as s:
            s.execute(text("DELETE FROM modulo1.definicion_requisito WHERE tenant_id = :t"), {"t": t.tenant_id})
        command.upgrade(cfg, "head")
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT conname FROM pg_constraint WHERE conname = 'uq_definicion_clave_negocio'")).scalar() == "uq_definicion_clave_negocio"
