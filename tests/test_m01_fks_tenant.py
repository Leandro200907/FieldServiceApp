"""M-01: claves foráneas compuestas por tenant (migración 0011).

Para cada relación: padre e hijo del mismo tenant → permitido; un UUID válido que
pertenece a OTRO tenant → PostgreSQL lo rechaza con SQLSTATE 23503 nombrando la
constraint compuesta. Más una inspección de pg_constraint que confirma que ninguna FK
tenant-scoped sigue siendo solo por UUID.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from psycopg.errors import ForeignKeyViolation
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import tenant_session
from tests import apoyo


def _ids(tenant, sufijo: str) -> dict:
    """Crea en el tenant un juego completo de padres y devuelve sus ids. Las claves de
    texto llevan sufijo por tenant para que "el id de otro tenant" sea realmente otro."""
    t = tenant.tenant_id
    P, V, OC = f"persona_{sufijo}", f"vehiculo_{sufijo}", f"OC-{sufijo}"
    with tenant_session(t) as s:
        apoyo.legajo(s, t, P); apoyo.legajo(s, t, V, "vehiculo"); apoyo.legajo(s, t, f"vehiculo2_{sufijo}", "vehiculo")
        req = str(s.execute(text("INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable) "
                                 "VALUES (:t, 'R', 'documento', 'persona') RETURNING requisito_definicion_id"), {"t": t}).scalar())
        doc = str(s.execute(text("INSERT INTO modulo1.documento (tenant_id, sujeto_id, requisito_definicion_id, vigente_desde, vigente_hasta, origen) "
                                 "VALUES (:t, :p, :r, '2026-01-01', '2026-12-31', 'carga_manual') RETURNING documento_id"), {"t": t, "r": req, "p": P}).scalar())
        req2 = str(s.execute(text("INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable) "
                                  "VALUES (:t, 'R2', 'documento', 'persona') RETURNING requisito_definicion_id"), {"t": t}).scalar())
        lote = str(s.execute(text("INSERT INTO modulo1.lote_importacion (tenant_id, origen, entidad, filas_totales, filas_aceptadas, filas_rechazadas) "
                                  "VALUES (:t, 'planilla', 'legajos', 0, 0, 0) RETURNING lote_id"), {"t": t}).scalar())
        matriz = str(s.execute(text("INSERT INTO modulo1.matriz_requisitos (tenant_id, cliente_id, locacion_id, tipo_servicio_id, version, vigente_desde) "
                                    "VALUES (:t, gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), 1, '2026-01-01') RETURNING matriz_version_id"), {"t": t}).scalar())
        ref = apoyo.evaluacion(s, t, OC)
        custodia = str(s.execute(text("INSERT INTO modulo1.custodia_recurso (tenant_id, recurso_id, tipo_recurso) VALUES (:t, :v, 'vehiculo') "
                                      "RETURNING custodia_id"), {"t": t, "v": V}).scalar())
        periodo = str(s.execute(text("INSERT INTO modulo1.periodo_custodia (tenant_id, custodia_id, custodio_id, desde, estado, hasta) "
                                     "VALUES (:t, :c, :p, '2026-01-01', 'cerrado', '2026-02-01') RETURNING periodo_id"), {"t": t, "c": custodia, "p": P}).scalar())
        constancia = str(s.execute(text("INSERT INTO modulo1.constancia_cliente (tenant_id, sujeto_id, requisito_definicion_id, cliente_id, registrada_por, evidencia) "
                                        "VALUES (:t, :p, :r, gen_random_uuid(), 'x', 'ev') RETURNING constancia_id"), {"t": t, "r": req, "p": P}).scalar())
        evento = str(s.execute(text("INSERT INTO modulo1.event_log (tenant_id, tipo, payload) VALUES (:t, 'X', '{}') RETURNING evento_id"), {"t": t}).scalar())
        aviso = str(s.execute(text("INSERT INTO modulo1.aviso_revaluacion (tenant_id, referencia_evaluacion, commitment_id) VALUES (:t, :r, :oc) "
                                   "RETURNING aviso_id"), {"t": t, "r": ref, "oc": OC}).scalar())
    return {"req": req, "req2": req2, "doc": doc, "lote": lote, "matriz": matriz, "ref": ref, "custodia": custodia, "periodo": periodo,
            "constancia": constancia, "evento": evento, "aviso": aviso, "usuario": tenant.usuarios["supervisor"], "sujeto": P,
            "vehiculo": f"vehiculo2_{sufijo}", "oc": OC, "persona": P, "ref_propia": ref}


# (nombre de la constraint, SQL de inserción del hijo, clave del padre en _ids)
RELACIONES = [
    ("fk_documento__requisito_definicion_id",
     "INSERT INTO modulo1.documento (tenant_id, sujeto_id, requisito_definicion_id, vigente_desde, vigente_hasta, origen, estado_version) VALUES (:t, :persona, :p, '2026-01-01', '2026-12-31', 'carga_manual', 'sucedida')", "req"),
    ("fk_documento__sucede_a",
     "INSERT INTO modulo1.documento (tenant_id, sujeto_id, vigente_desde, vigente_hasta, origen, sucede_a, estado_version) VALUES (:t, :persona, '2026-01-01', '2026-12-31', 'carga_manual', :p, 'sucedida')", "doc"),
    ("fk_documento__lote_id",
     "INSERT INTO modulo1.documento (tenant_id, sujeto_id, vigente_desde, vigente_hasta, origen, lote_id) VALUES (:t, :persona, '2026-01-01', '2026-12-31', 'planilla', :p)", "lote"),
    ("fk_documento__sujeto_id",
     "INSERT INTO modulo1.documento (tenant_id, sujeto_id, vigente_desde, vigente_hasta, origen) VALUES (:t, :p, '2026-01-01', '2026-12-31', 'carga_manual')", "sujeto"),
    ("fk_acreditacion_competencia__requisito_definicion_id",
     "INSERT INTO modulo1.acreditacion_competencia (tenant_id, persona_id, requisito_definicion_id, vigente_desde, vigente_hasta, evidencias) VALUES (:t, :persona, :p, '2026-01-01', '2026-12-31', ARRAY[gen_random_uuid()])", "req"),
    ("fk_acreditacion_competencia__persona_id",
     "INSERT INTO modulo1.acreditacion_competencia (tenant_id, persona_id, requisito_definicion_id, vigente_desde, vigente_hasta, evidencias) VALUES (:t, :p, :req, '2026-01-01', '2026-12-31', ARRAY[gen_random_uuid()])", "sujeto"),
    ("fk_induccion__evidencia",
     "INSERT INTO modulo1.induccion (tenant_id, persona_id, locacion_id, requisito_definicion_id, vigente_desde, vigente_hasta, evidencia) VALUES (:t, :persona, gen_random_uuid(), :req, '2026-01-01', '2026-12-31', :p)", "doc"),
    ("fk_induccion__persona_id",
     "INSERT INTO modulo1.induccion (tenant_id, persona_id, locacion_id, requisito_definicion_id, vigente_desde, vigente_hasta, evidencia) VALUES (:t, :p, gen_random_uuid(), :req, '2026-01-01', '2026-12-31', :doc)", "sujeto"),
    ("fk_linea_requisito__matriz_version_id",
     "INSERT INTO modulo1.linea_requisito (tenant_id, matriz_version_id, requisito_definicion_id, clasificacion, bloqueante_durante_ejecucion) VALUES (:t, :p, :req2, 'excepcionable', true)", "matriz"),
    ("fk_requisito_particular__commitment_id",
     "INSERT INTO modulo1.requisito_particular (tenant_id, commitment_id, requisito_definicion_id, clasificacion, bloqueante_durante_ejecucion) VALUES (:t, :p, :req2, 'excepcionable', true)", "oc"),
    ("fk_custodia_recurso__recurso_id",
     "INSERT INTO modulo1.custodia_recurso (tenant_id, recurso_id, tipo_recurso) VALUES (:t, :p, 'vehiculo')", "vehiculo"),
    ("fk_periodo_custodia__custodia_id",
     "INSERT INTO modulo1.periodo_custodia (tenant_id, custodia_id, custodio_id, desde, estado, hasta) VALUES (:t, :p, :persona, '2026-03-01', 'cerrado', '2026-04-01')", "custodia"),
    ("fk_periodo_custodia__custodio_id",
     "INSERT INTO modulo1.periodo_custodia (tenant_id, custodia_id, custodio_id, desde, estado, hasta) VALUES (:t, :custodia, :p, '2026-03-01', 'cerrado', '2026-04-01')", "sujeto"),
    ("fk_periodo_custodia__corregido_por",
     "INSERT INTO modulo1.periodo_custodia (tenant_id, custodia_id, custodio_id, desde, estado, hasta, corregido_por) VALUES (:t, :custodia, :persona, '2026-05-01', 'corregido', '2026-06-01', :p)", "periodo"),
    ("fk_excepcion__referencia_evaluacion",
     "INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, commitment_id, otorgada_por, motivo, estado) VALUES (:t, :p, :persona, :req, :oc, 'u', 'm', 'revocada')", "ref"),
    ("fk_excepcion__sujeto_id",
     "INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, commitment_id, otorgada_por, motivo, estado) VALUES (:t, :ref, :p, :req, :oc, 'u', 'm', 'revocada')", "sujeto"),
    ("fk_excepcion__commitment_id",
     "INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, commitment_id, otorgada_por, motivo, estado) VALUES (:t, :ref, :persona, :req, :p, 'u', 'm', 'revocada')", "oc"),
    ("fk_constancia_cliente__reemplazada_por",
     "INSERT INTO modulo1.constancia_cliente (tenant_id, sujeto_id, requisito_definicion_id, cliente_id, registrada_por, evidencia, estado, reemplazada_por) VALUES (:t, :persona, :req, gen_random_uuid(), 'x', 'ev', 'reemplazada', :p)", "constancia"),
    ("fk_constancia_cliente__sujeto_id",
     "INSERT INTO modulo1.constancia_cliente (tenant_id, sujeto_id, requisito_definicion_id, cliente_id, registrada_por, evidencia, estado) VALUES (:t, :p, :req, gen_random_uuid(), 'x', 'ev', 'revocada')", "sujeto"),
    ("fk_constancia_cliente__commitment_id",
     "INSERT INTO modulo1.constancia_cliente (tenant_id, sujeto_id, requisito_definicion_id, cliente_id, commitment_id, registrada_por, evidencia, estado) VALUES (:t, :persona, :req, gen_random_uuid(), :p, 'x', 'ev', 'revocada')", "oc"),
    ("fk_evaluacion_habilitacion__commitment_id",
     "INSERT INTO modulo1.evaluacion_habilitacion (tenant_id, commitment_id, veredicto_de_cumplimiento, resultado_de_decision, por_sujeto, snapshot) VALUES (:t, :p, 'no_habilitado', 'no_puede_asignarse', '[]', '{}')", "oc"),
    ("fk_aviso_revaluacion__cerrado_por_referencia",
     "INSERT INTO modulo1.aviso_revaluacion (tenant_id, referencia_evaluacion, commitment_id, estado, cerrado_en, cerrado_por_referencia) VALUES (:t, :ref_propia, :oc, 'cerrado', now(), :p)", "ref"),
    ("fk_aviso_revaluacion_causa__evento_id",
     "INSERT INTO modulo1.aviso_revaluacion_causa (tenant_id, aviso_id, evento_id, tipo_evento, entidad_tipo, entidad_id) VALUES (:t, :aviso, :p, 'X', 'x', 'x')", "evento"),
    ("fk_oc__lote_id",
     "INSERT INTO modulo1.oc (tenant_id, clave_origen, cliente_id, locacion_id, tipo_servicio_id, vigencia_desde, vigencia_hasta, lote_id) VALUES (:t, 'OC-' || gen_random_uuid()::text, gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), '2026-01-01', '2026-02-01', :p)", "lote"),
    ("fk_refresh_token__usuario_id",
     "INSERT INTO modulo1.refresh_token (token_hash, tenant_id, usuario_id, expira_en) VALUES (gen_random_uuid()::text, :t, :p, now() + interval '1 day')", "usuario"),
    ("fk_asignacion_supervisor__sujeto_id",
     "INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por, estado, hasta) VALUES (:t, :p, :usuario, '2026-01-01', 'x', 'cerrada', '2026-02-01')", "sujeto"),
    ("fk_asignacion_supervisor__supervisor_usuario_id",
     "INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por, estado, hasta) VALUES (:t, :persona, :p, '2026-01-01', 'x', 'cerrada', '2026-02-01')", "usuario"),
]


@pytest.mark.parametrize("constraint,sql,padre", RELACIONES, ids=[r[0] for r in RELACIONES])
def test_fk_compuesta_mismo_tenant_permitido_y_otro_tenant_rechazado(dos_tenants, constraint, sql, padre):
    ta, tb = dos_tenants
    ida, idb = _ids(ta, "A"), _ids(tb, "B")
    # mismo tenant → permitido
    with tenant_session(ta.tenant_id) as s:
        s.execute(text(sql), {"t": ta.tenant_id, "p": ida[padre], **{k: v for k, v in ida.items() if k != padre}})
    # id válido pero de otro tenant → 23503 nombrando la constraint compuesta
    with pytest.raises(IntegrityError) as e:
        with tenant_session(ta.tenant_id) as s:
            s.execute(text(sql), {"t": ta.tenant_id, "p": idb[padre], **{k: v for k, v in ida.items() if k != padre}})
    assert isinstance(e.value.orig, ForeignKeyViolation) and e.value.orig.sqlstate == "23503"
    assert e.value.orig.diag.constraint_name == constraint


def test_pg_constraint_no_quedan_fks_simples_tenant_scoped():
    """Toda FK de una tabla tenant-scoped hacia otra tabla tenant-scoped incluye tenant_id
    (las únicas FKs de una sola columna son las que apuntan a `tenant` o a `plataforma`)."""
    with tenant_session(str(uuid.uuid4())) as s:
        filas = s.execute(text(
            "SELECT c.conrelid::regclass::text AS hija, c.confrelid::regclass::text AS padre, c.conname, "
            "       array_length(c.conkey, 1) AS n, "
            "       (SELECT string_agg(a.attname, ',' ORDER BY k.ord) FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ord) "
            "        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum) AS cols "
            "FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace WHERE n.nspname = 'modulo1' AND c.contype = 'f'"
        )).mappings().all()
    assert len(filas) >= 45
    for f in filas:
        if f["padre"] in ("modulo1.tenant",) or f["padre"].startswith("plataforma."):
            continue
        assert f["n"] >= 2 and f["cols"].startswith("tenant_id,"), (f["hija"], f["conname"], f["cols"])
    # las dos correcciones de ON DELETE: períodos y causas ya no caen en cascada
    with tenant_session(str(uuid.uuid4())) as s:
        deltypes = dict(s.execute(text("SELECT conname, confdeltype FROM pg_constraint WHERE conname IN "
                                       "('fk_periodo_custodia__custodia_id', 'fk_aviso_revaluacion_causa__evento_id', 'fk_linea_requisito__matriz_version_id')")).all())
    assert deltypes == {"fk_periodo_custodia__custodia_id": "a", "fk_aviso_revaluacion_causa__evento_id": "a",
                        "fk_linea_requisito__matriz_version_id": "c"}
