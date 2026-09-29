"""Unifica documentos, competencias e inducciones en una sola entidad documental.

Revision ID: 0023_documento_unificado
Revises: 0022_espejo_operadoras
"""
import sqlalchemy as sa
from alembic import op


revision = "0023_documento_unificado"
down_revision = "0022_espejo_operadoras"
branch_labels = None
depends_on = None

_POLICY = (
    "USING (tenant_id = current_setting('app.current_tenant')::uuid) "
    "WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)"
)

_SQL_TABLAS_FORCE = (
    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'modulo1' AND c.relkind = 'r' AND c.relforcerowsecurity"
)


def _sin_force_rls(fn):
    """Copia cruzando tenants: FORCE RLS + sin `app.current_tenant` deja 0 filas visibles
    o aborta. Igual que 0011/0021, se suspende FORCE sólo durante la copia."""
    conn = op.get_bind()
    tablas = [r[0] for r in conn.execute(sa.text(_SQL_TABLAS_FORCE))]
    for t in tablas:
        op.execute(f"ALTER TABLE modulo1.{t} NO FORCE ROW LEVEL SECURITY")
    try:
        fn()
    finally:
        for t in tablas:
            op.execute(f"ALTER TABLE modulo1.{t} FORCE ROW LEVEL SECURITY")


def _contar(sql: str) -> int:
    return int(op.get_bind().execute(sa.text(sql)).scalar() or 0)


def _exigir_conteo(esperado: int, obtenido: int, que: str) -> None:
    if esperado != obtenido:
        raise RuntimeError(
            f"Migración 0023 abortada: {que} esperadas={esperado} copiadas={obtenido}"
        )


def upgrade() -> None:
    # `documento` pasa a ser la entidad canónica para las tres categorías definidas en
    # definicion_requisito. La locación sólo se completa para una inducción.
    op.execute("ALTER TABLE modulo1.documento ADD COLUMN locacion_id UUID")
    op.execute("ALTER TABLE modulo1.documento ALTER COLUMN vigente_hasta DROP NOT NULL")
    op.execute("ALTER TABLE modulo1.documento DROP CONSTRAINT ck_vigencia_documento")
    op.execute(
        "ALTER TABLE modulo1.documento ADD CONSTRAINT ck_vigencia_documento "
        "CHECK (vigente_hasta IS NULL OR vigente_desde <= vigente_hasta)"
    )

    # Una competencia o inducción puede apoyarse en uno o más documentos ya cargados.
    # La relación reemplaza acreditacion.evidencias[] e induccion.evidencia.
    op.execute("""
        CREATE TABLE modulo1.documento_soporte (
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            documento_id UUID NOT NULL,
            soporte_documento_id UUID NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, documento_id, soporte_documento_id),
            CONSTRAINT fk_documento_soporte__documento_id
            FOREIGN KEY (tenant_id, documento_id)
                REFERENCES modulo1.documento(tenant_id, documento_id) ON DELETE CASCADE,
            CONSTRAINT fk_documento_soporte__soporte_documento_id
            FOREIGN KEY (tenant_id, soporte_documento_id)
                REFERENCES modulo1.documento(tenant_id, documento_id),
            CHECK (documento_id <> soporte_documento_id)
        )
    """)

    # Las filas se insertan primero como históricas para respetar el índice que permite
    # una sola versión vigente. Luego se promueve la más reciente si la clave no tenía
    # ya una versión vigente en documento.
    _sin_force_rls(_copiar_acreditaciones_e_inducciones)

    op.execute("DROP TABLE modulo1.acreditacion_competencia")
    op.execute("DROP TABLE modulo1.induccion")

    op.execute("ALTER TABLE modulo1.documento_soporte ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.documento_soporte FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY documento_soporte_aislamiento ON modulo1.documento_soporte {_POLICY}")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON modulo1.documento_soporte TO modulo1_app")


def _copiar_acreditaciones_e_inducciones() -> None:
    n_acc = _contar("SELECT count(*) FROM modulo1.acreditacion_competencia")
    n_ind = _contar("SELECT count(*) FROM modulo1.induccion")
    op.execute("""
        INSERT INTO modulo1.documento (
            documento_id, tenant_id, sujeto_id, requisito_definicion_id,
            vigente_desde, vigente_hasta, estado_confirmacion, estado_version,
            origen_propuesta, version, origen, creado_en
        )
        SELECT a.acreditacion_id, a.tenant_id, a.persona_id, a.requisito_definicion_id,
               a.vigente_desde, a.vigente_hasta, a.estado_confirmacion, 'sucedida',
               false,
               COALESCE((
                   SELECT max(existente.version)
                   FROM modulo1.documento existente
                   WHERE existente.tenant_id = a.tenant_id
                     AND existente.sujeto_id = a.persona_id
                     AND existente.requisito_definicion_id = a.requisito_definicion_id
               ), 0) + row_number() OVER (
                   PARTITION BY a.tenant_id, a.persona_id, a.requisito_definicion_id
                   ORDER BY a.vigente_hasta, a.creado_en, a.acreditacion_id
               ),
               'carga_manual', a.creado_en
        FROM modulo1.acreditacion_competencia a
    """)
    op.execute("""
        INSERT INTO modulo1.documento_soporte (tenant_id, documento_id, soporte_documento_id)
        SELECT a.tenant_id, a.acreditacion_id, evidencia
        FROM modulo1.acreditacion_competencia a
        CROSS JOIN LATERAL unnest(a.evidencias) AS evidencia
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO modulo1.documento (
            documento_id, tenant_id, sujeto_id, requisito_definicion_id, locacion_id,
            vigente_desde, vigente_hasta, estado_confirmacion, estado_version,
            origen_propuesta, version, origen, creado_en
        )
        SELECT i.induccion_id, i.tenant_id, i.persona_id, i.requisito_definicion_id, i.locacion_id,
               i.vigente_desde, i.vigente_hasta, i.estado_confirmacion, 'sucedida',
               false,
               COALESCE((
                   SELECT max(existente.version)
                   FROM modulo1.documento existente
                   WHERE existente.tenant_id = i.tenant_id
                     AND existente.sujeto_id = i.persona_id
                     AND existente.requisito_definicion_id = i.requisito_definicion_id
               ), 0) + row_number() OVER (
                   PARTITION BY i.tenant_id, i.persona_id, i.requisito_definicion_id
                   ORDER BY i.vigente_hasta, i.creado_en, i.induccion_id
               ),
               'carga_manual', i.creado_en
        FROM modulo1.induccion i
    """)
    op.execute("""
        INSERT INTO modulo1.documento_soporte (tenant_id, documento_id, soporte_documento_id)
        SELECT tenant_id, induccion_id, evidencia FROM modulo1.induccion
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        WITH migradas AS (
            SELECT tenant_id, acreditacion_id AS documento_id, persona_id AS sujeto_id,
                   requisito_definicion_id, vigente_hasta, creado_en
            FROM modulo1.acreditacion_competencia
            UNION ALL
            SELECT tenant_id, induccion_id, persona_id, requisito_definicion_id,
                   vigente_hasta, creado_en
            FROM modulo1.induccion
        ), elegidas AS (
            SELECT DISTINCT ON (m.tenant_id, m.sujeto_id, m.requisito_definicion_id)
                   m.tenant_id, m.documento_id
            FROM migradas m
            WHERE NOT EXISTS (
                SELECT 1 FROM modulo1.documento actual
                WHERE actual.tenant_id = m.tenant_id
                  AND actual.sujeto_id = m.sujeto_id
                  AND actual.requisito_definicion_id = m.requisito_definicion_id
                  AND actual.estado_version = 'vigente'
            )
            ORDER BY m.tenant_id, m.sujeto_id, m.requisito_definicion_id,
                     m.vigente_hasta DESC NULLS FIRST, m.creado_en DESC, m.documento_id DESC
        )
        UPDATE modulo1.documento d SET estado_version = 'vigente'
        FROM elegidas e
        WHERE d.tenant_id = e.tenant_id AND d.documento_id = e.documento_id
    """)
    _exigir_conteo(
        n_acc,
        _contar(
            "SELECT count(*) FROM modulo1.documento d "
            "JOIN modulo1.acreditacion_competencia a "
            "ON a.tenant_id = d.tenant_id AND a.acreditacion_id = d.documento_id"
        ),
        "acreditaciones",
    )
    _exigir_conteo(
        n_ind,
        _contar(
            "SELECT count(*) FROM modulo1.documento d "
            "JOIN modulo1.induccion i "
            "ON i.tenant_id = d.tenant_id AND i.induccion_id = d.documento_id"
        ),
        "inducciones",
    )


def downgrade() -> None:
    op.execute("""
        CREATE TABLE modulo1.acreditacion_competencia (
            acreditacion_id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            persona_id TEXT NOT NULL,
            requisito_definicion_id UUID NOT NULL,
            vigente_desde DATE NOT NULL,
            vigente_hasta DATE NOT NULL,
            estado_confirmacion TEXT NOT NULL,
            evidencias UUID[] NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE modulo1.induccion (
            induccion_id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            persona_id TEXT NOT NULL,
            locacion_id UUID NOT NULL,
            requisito_definicion_id UUID NOT NULL,
            vigente_desde DATE NOT NULL,
            vigente_hasta DATE NOT NULL,
            estado_confirmacion TEXT NOT NULL,
            evidencia UUID NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    _sin_force_rls(_restaurar_acreditaciones_e_inducciones)
    op.execute("DROP TABLE modulo1.documento_soporte")
    op.execute("ALTER TABLE modulo1.documento DROP COLUMN locacion_id")
    op.execute("ALTER TABLE modulo1.documento ALTER COLUMN vigente_hasta SET NOT NULL")
    op.execute("ALTER TABLE modulo1.documento DROP CONSTRAINT ck_vigencia_documento")
    op.execute("ALTER TABLE modulo1.documento ADD CONSTRAINT ck_vigencia_documento CHECK (vigente_desde <= vigente_hasta)")


def _restaurar_acreditaciones_e_inducciones() -> None:
    n_acc = _contar(
        "SELECT count(*) FROM modulo1.documento d "
        "JOIN modulo1.definicion_requisito r "
        "ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id "
        "WHERE r.categoria = 'competencia' AND d.vigente_hasta IS NOT NULL"
    )
    n_ind = _contar(
        "SELECT count(*) FROM modulo1.documento d "
        "JOIN modulo1.definicion_requisito r "
        "ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id "
        "WHERE r.categoria = 'induccion' AND d.vigente_hasta IS NOT NULL AND d.locacion_id IS NOT NULL"
    )
    op.execute("""
        INSERT INTO modulo1.acreditacion_competencia
        SELECT d.documento_id, d.tenant_id, d.sujeto_id, d.requisito_definicion_id,
               d.vigente_desde, d.vigente_hasta, d.estado_confirmacion,
               ARRAY(SELECT ds.soporte_documento_id FROM modulo1.documento_soporte ds
                     WHERE ds.tenant_id = d.tenant_id AND ds.documento_id = d.documento_id),
               d.creado_en
        FROM modulo1.documento d
        JOIN modulo1.definicion_requisito r
          ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
        WHERE r.categoria = 'competencia' AND d.vigente_hasta IS NOT NULL
    """)
    op.execute("""
        INSERT INTO modulo1.induccion
        SELECT d.documento_id, d.tenant_id, d.sujeto_id, d.locacion_id,
               d.requisito_definicion_id, d.vigente_desde, d.vigente_hasta,
               d.estado_confirmacion,
               (SELECT ds.soporte_documento_id FROM modulo1.documento_soporte ds
                WHERE ds.tenant_id = d.tenant_id AND ds.documento_id = d.documento_id LIMIT 1),
               d.creado_en
        FROM modulo1.documento d
        JOIN modulo1.definicion_requisito r
          ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
        WHERE r.categoria = 'induccion' AND d.vigente_hasta IS NOT NULL AND d.locacion_id IS NOT NULL
    """)
    _exigir_conteo(n_acc, _contar("SELECT count(*) FROM modulo1.acreditacion_competencia"), "acreditaciones restauradas")
    _exigir_conteo(n_ind, _contar("SELECT count(*) FROM modulo1.induccion"), "inducciones restauradas")
    op.execute(
        "DELETE FROM modulo1.documento d USING modulo1.definicion_requisito r "
        "WHERE r.tenant_id=d.tenant_id AND r.requisito_definicion_id=d.requisito_definicion_id "
        "AND r.categoria IN ('competencia','induccion')"
    )

