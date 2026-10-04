"""E-20: estado_version propuesta para renovaciones del técnico sin suceder al vigente.

Revision ID: 0031_documento_estado_propuesta
Revises: 0030_legajo_nombre_apellido
"""
from alembic import op

revision = "0031_documento_estado_propuesta"
down_revision = "0030_legajo_nombre_apellido"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE modulo1.documento NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "ALTER TABLE modulo1.documento DROP CONSTRAINT IF EXISTS documento_estado_version_check"
    )
    op.execute(
        """
        ALTER TABLE modulo1.documento
        ADD CONSTRAINT documento_estado_version_check
        CHECK (estado_version IN (
            'vigente', 'sucedida', 'rechazada', 'revertida_por_lote', 'propuesta'
        ))
        """
    )

    # Propuestas que ocupaban el slot vigente → propuesta; restaurar el antecesor sucedido.
    op.execute(
        """
        UPDATE modulo1.documento p
        SET estado_version = 'propuesta'
        WHERE p.origen_propuesta = true
          AND p.estado_confirmacion = 'declarado'
          AND p.estado_version = 'vigente'
        """
    )
    op.execute(
        """
        UPDATE modulo1.documento ant
        SET estado_version = 'vigente',
            dejo_de_ser_vigente_en = NULL
        FROM modulo1.documento p
        WHERE p.origen_propuesta = true
          AND p.estado_confirmacion = 'declarado'
          AND p.estado_version = 'propuesta'
          AND p.sucede_a IS NOT NULL
          AND ant.documento_id = p.sucede_a
          AND ant.estado_version = 'sucedida'
        """
    )
    # Propuestas sin sucede_a: solo pasan a propuesta; no hay vigente que restaurar
    # (p. ej. primera renovación sin enlace o datos demo inconsistentes).

    op.execute(
        """
        CREATE UNIQUE INDEX uq_documento_propuesta_pendiente
        ON modulo1.documento (tenant_id, sujeto_id, requisito_definicion_id)
        WHERE estado_version = 'propuesta' AND requisito_definicion_id IS NOT NULL
        """
    )
    op.execute("ALTER TABLE modulo1.documento FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE modulo1.documento NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS modulo1.uq_documento_propuesta_pendiente")
    op.execute(
        """
        UPDATE modulo1.documento
        SET estado_version = 'vigente'
        WHERE estado_version = 'propuesta'
        """
    )
    op.execute(
        "ALTER TABLE modulo1.documento DROP CONSTRAINT IF EXISTS documento_estado_version_check"
    )
    op.execute(
        """
        ALTER TABLE modulo1.documento
        ADD CONSTRAINT documento_estado_version_check
        CHECK (estado_version IN (
            'vigente', 'sucedida', 'rechazada', 'revertida_por_lote'
        ))
        """
    )
    op.execute("ALTER TABLE modulo1.documento FORCE ROW LEVEL SECURITY")
