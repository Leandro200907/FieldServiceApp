"""M-01: claves foráneas compuestas por tenant.

Cada relación tenant-scoped pasa de referenciar solo el UUID del padre a referenciar
`(tenant_id, id_padre)`: la base prueba que padre e hijo son del mismo tenant aunque RLS
no estuviera. Reglas aplicadas:
- el padre recibe UNIQUE (tenant_id, id) donde faltaba;
- la política ON DELETE se conserva, salvo dos correcciones: `custodia_recurso →
  periodo_custodia` deja de ser CASCADE (los períodos son historial) y
  `event_log → aviso_revaluacion_causa` deja de ser CASCADE (la causa es auditoría);
- ningún CASCADE nuevo.
Excepciones intencionales documentadas en docs/DECISIONES_DOMINIO.md §10.

Sin datos productivos y sin huérfanos/cruces en las bases existentes (relevamiento del
2026-09-19); si una base tuviera cruces, las ADD CONSTRAINT fallan y la migración aborta
sin tocar datos.

Revision ID: 0011_tenant_fks
Revises: 0010_outbox_revaluacion
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_tenant_fks"
down_revision = "0010_outbox_revaluacion"
branch_labels = None
depends_on = None

# (tabla, constraint vieja, columnas hija, tabla padre, columnas padre, on_delete)
FKS = [
    ("documento", "documento_requisito_definicion_id_fkey", "tenant_id, requisito_definicion_id", "definicion_requisito", "tenant_id, requisito_definicion_id", "NO ACTION"),
    ("documento", "documento_sucede_a_fkey", "tenant_id, sucede_a", "documento", "tenant_id, documento_id", "NO ACTION"),
    ("documento", "documento_lote_id_fkey", "tenant_id, lote_id", "lote_importacion", "tenant_id, lote_id", "NO ACTION"),
    ("documento", None, "tenant_id, sujeto_id", "legajo", "tenant_id, sujeto_id", "NO ACTION"),
    ("acreditacion_competencia", "acreditacion_competencia_requisito_definicion_id_fkey", "tenant_id, requisito_definicion_id", "definicion_requisito", "tenant_id, requisito_definicion_id", "NO ACTION"),
    ("acreditacion_competencia", None, "tenant_id, persona_id", "legajo", "tenant_id, sujeto_id", "NO ACTION"),
    ("induccion", "induccion_requisito_definicion_id_fkey", "tenant_id, requisito_definicion_id", "definicion_requisito", "tenant_id, requisito_definicion_id", "NO ACTION"),
    ("induccion", "induccion_evidencia_fkey", "tenant_id, evidencia", "documento", "tenant_id, documento_id", "NO ACTION"),
    ("induccion", None, "tenant_id, persona_id", "legajo", "tenant_id, sujeto_id", "NO ACTION"),
    ("linea_requisito", "linea_requisito_matriz_version_id_fkey", "tenant_id, matriz_version_id", "matriz_requisitos", "tenant_id, matriz_version_id", "CASCADE"),
    ("linea_requisito", "linea_requisito_requisito_definicion_id_fkey", "tenant_id, requisito_definicion_id", "definicion_requisito", "tenant_id, requisito_definicion_id", "NO ACTION"),
    ("requisito_particular", "requisito_particular_requisito_definicion_id_fkey", "tenant_id, requisito_definicion_id", "definicion_requisito", "tenant_id, requisito_definicion_id", "NO ACTION"),
    ("requisito_particular", None, "tenant_id, commitment_id", "oc", "tenant_id, clave_origen", "NO ACTION"),
    ("custodia_recurso", None, "tenant_id, recurso_id", "legajo", "tenant_id, sujeto_id", "NO ACTION"),
    ("periodo_custodia", "periodo_custodia_custodia_id_fkey", "tenant_id, custodia_id", "custodia_recurso", "tenant_id, custodia_id", "NO ACTION"),
    ("periodo_custodia", "periodo_custodia_corregido_por_fkey", "tenant_id, corregido_por", "periodo_custodia", "tenant_id, periodo_id", "NO ACTION"),
    ("periodo_custodia", None, "tenant_id, custodio_id", "legajo", "tenant_id, sujeto_id", "NO ACTION"),
    ("excepcion", "excepcion_requisito_definicion_id_fkey", "tenant_id, requisito_definicion_id", "definicion_requisito", "tenant_id, requisito_definicion_id", "NO ACTION"),
    ("excepcion", None, "tenant_id, referencia_evaluacion", "evaluacion_habilitacion", "tenant_id, referencia_evaluacion", "NO ACTION"),
    ("excepcion", None, "tenant_id, sujeto_id", "legajo", "tenant_id, sujeto_id", "NO ACTION"),
    ("excepcion", None, "tenant_id, commitment_id", "oc", "tenant_id, clave_origen", "NO ACTION"),
    ("constancia_cliente", "constancia_cliente_requisito_definicion_id_fkey", "tenant_id, requisito_definicion_id", "definicion_requisito", "tenant_id, requisito_definicion_id", "NO ACTION"),
    ("constancia_cliente", "constancia_cliente_reemplazada_por_fkey", "tenant_id, reemplazada_por", "constancia_cliente", "tenant_id, constancia_id", "NO ACTION"),
    ("constancia_cliente", None, "tenant_id, sujeto_id", "legajo", "tenant_id, sujeto_id", "NO ACTION"),
    ("constancia_cliente", None, "tenant_id, commitment_id", "oc", "tenant_id, clave_origen", "NO ACTION"),
    ("evaluacion_habilitacion", None, "tenant_id, commitment_id", "oc", "tenant_id, clave_origen", "NO ACTION"),
    ("aviso_revaluacion", None, "tenant_id, commitment_id", "oc", "tenant_id, clave_origen", "NO ACTION"),
    ("aviso_revaluacion", None, "tenant_id, cerrado_por_referencia", "evaluacion_habilitacion", "tenant_id, referencia_evaluacion", "NO ACTION"),
    ("aviso_revaluacion_causa", "fk_arc_evento", "tenant_id, evento_id", "event_log", "tenant_id, evento_id", "NO ACTION"),
    ("oc", "oc_lote_id_fkey", "tenant_id, lote_id", "lote_importacion", "tenant_id, lote_id", "NO ACTION"),
    ("refresh_token", "refresh_token_usuario_id_fkey", "tenant_id, usuario_id", "usuario", "tenant_id, usuario_id", "NO ACTION"),
    ("asignacion_supervisor", None, "tenant_id, sujeto_id", "legajo", "tenant_id, sujeto_id", "NO ACTION"),
    ("asignacion_supervisor", None, "tenant_id, supervisor_usuario_id", "usuario", "tenant_id, usuario_id", "NO ACTION"),
]

# UNIQUE (tenant_id, id) que faltan en los padres.
UNIQUES = [
    ("documento", "uq_documento_tenant_id", "tenant_id, documento_id"),
    ("lote_importacion", "uq_lote_tenant_id", "tenant_id, lote_id"),
    ("matriz_requisitos", "uq_matriz_tenant_id", "tenant_id, matriz_version_id"),
    ("custodia_recurso", "uq_custodia_tenant_id", "tenant_id, custodia_id"),
    ("periodo_custodia", "uq_periodo_tenant_id", "tenant_id, periodo_id"),
    ("constancia_cliente", "uq_constancia_tenant_id", "tenant_id, constancia_id"),
    ("usuario", "uq_usuario_tenant_id", "tenant_id, usuario_id"),
]


def _nombre(tabla: str, columnas: str) -> str:
    return "fk_" + tabla + "__" + columnas.split(",")[1].strip()


_SQL_TABLAS_FORCE = (
    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'modulo1' AND c.relkind = 'r' AND c.relforcerowsecurity"
)


def _sin_force_rls(fn):
    """ADD CONSTRAINT valida las filas existentes leyéndolas a través de RLS; con FORCE el
    owner tampoco las ve (y `app.current_tenant` no está fijado en la migración). Para que
    la validación sea un escaneo completo real —y no "cero filas visibles"— se suspende
    FORCE dentro de la transacción de la migración y se restaura al final."""
    conn = op.get_bind()
    tablas = [r[0] for r in conn.execute(sa.text(_SQL_TABLAS_FORCE))]
    for t in tablas:
        op.execute(f"ALTER TABLE modulo1.{t} NO FORCE ROW LEVEL SECURITY")
    try:
        fn()
    finally:
        for t in tablas:
            op.execute(f"ALTER TABLE modulo1.{t} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    _sin_force_rls(_upgrade)


def _upgrade() -> None:
    for tabla, nombre, cols in UNIQUES:
        op.execute(f"ALTER TABLE modulo1.{tabla} ADD CONSTRAINT {nombre} UNIQUE ({cols})")
    # oc: UNIQUE (tenant_id, clave_origen) ya existe como constraint `uq_oc_clave_origen` (0003).
    for tabla, vieja, cols, padre, pcols, on_delete in FKS:
        if vieja:
            op.execute(f"ALTER TABLE modulo1.{tabla} DROP CONSTRAINT {vieja}")
        op.execute(
            f"ALTER TABLE modulo1.{tabla} ADD CONSTRAINT {_nombre(tabla, cols)} "
            f"FOREIGN KEY ({cols}) REFERENCES modulo1.{padre} ({pcols}) ON DELETE {on_delete}"
        )
    # Índices de soporte para las FKs nuevas sobre columnas sin índice previo.
    for tabla, cols in (
        ("documento", "tenant_id, sujeto_id"), ("acreditacion_competencia", "tenant_id, persona_id"),
        ("induccion", "tenant_id, persona_id"), ("periodo_custodia", "tenant_id, custodio_id"),
        ("excepcion", "tenant_id, referencia_evaluacion"), ("excepcion", "tenant_id, sujeto_id"),
        ("excepcion", "tenant_id, commitment_id"), ("constancia_cliente", "tenant_id, sujeto_id"),
        ("constancia_cliente", "tenant_id, commitment_id"), ("requisito_particular", "tenant_id, commitment_id"),
        ("asignacion_supervisor", "tenant_id, sujeto_id"),
    ):
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{tabla}__{cols.split(',')[1].strip()} ON modulo1.{tabla} ({cols})")


def downgrade() -> None:
    _sin_force_rls(_downgrade)


def _downgrade() -> None:
    for tabla, vieja, cols, padre, pcols, on_delete in reversed(FKS):
        op.execute(f"ALTER TABLE modulo1.{tabla} DROP CONSTRAINT IF EXISTS {_nombre(tabla, cols)}")
        if vieja:
            simple = cols.split(",")[1].strip()
            psimple = pcols.split(",")[1].strip()
            od = "CASCADE" if vieja in ("linea_requisito_matriz_version_id_fkey", "periodo_custodia_custodia_id_fkey", "fk_arc_evento") else "NO ACTION"
            ref = f"({psimple})" if vieja != "fk_arc_evento" else "(tenant_id, evento_id)"
            col = f"({simple})" if vieja != "fk_arc_evento" else "(tenant_id, evento_id)"
            op.execute(f"ALTER TABLE modulo1.{tabla} ADD CONSTRAINT {vieja} FOREIGN KEY {col} REFERENCES modulo1.{padre} {ref} ON DELETE {od}")
    for tabla, nombre, cols in reversed(UNIQUES):
        op.execute(f"ALTER TABLE modulo1.{tabla} DROP CONSTRAINT IF EXISTS {nombre}")
