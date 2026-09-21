"""H-01: capacidades v1 que faltaban (anexo "Alcance de la v1" de documentacion-habilitante).

- Notificaciones reales: `configuracion_canales` por tenant (mail / Telegram habilitados,
  remitente), `usuario.telegram_chat_id`, `notificacion_envio` (traza idempotente por
  job + canal + destinatario: at-least-once sin duplicados, M-07).
- Paquete de entrega público con QR: `paquete_entrega` (token no enumerable, vencimiento,
  revocación, traza de accesos en `paquete_acceso`).
- Score de salud documental: `score_snapshot` (histórico diario por tenant, calculado por
  el worker en la cola `score_documental`).
- Drive de solo lectura: `configuracion_drive` por tenant (carpeta, programación),
  `archivo_drive` (cada archivo visto: extracción de tipo/sujeto/fecha por confianza,
  estado y bandeja de excepciones), `documento.archivo_drive_id`.
- Exportación de legajo: sin tabla; deja traza `LegajoExportado` en el event_log.

Revision ID: 0018_capacidades_v1
Revises: 0017_alertas_vencimiento
"""
from alembic import op

revision = "0018_capacidades_v1"
down_revision = "0017_alertas_vencimiento"
branch_labels = None
depends_on = None

_POLICY = (
    "USING (tenant_id = current_setting('app.current_tenant')::uuid) "
    "WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)"
)


def _rls(tabla: str) -> None:
    op.execute(f"ALTER TABLE modulo1.{tabla} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE modulo1.{tabla} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {tabla}_aislamiento ON modulo1.{tabla} {_POLICY}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON modulo1.{tabla} TO modulo1_app")


def upgrade() -> None:
    # --- notificaciones ---------------------------------------------------------
    op.execute(
        """
        CREATE TABLE modulo1.configuracion_canales (
            tenant_id UUID PRIMARY KEY REFERENCES modulo1.tenant(tenant_id),
            mail_habilitado BOOLEAN NOT NULL DEFAULT false,
            telegram_habilitado BOOLEAN NOT NULL DEFAULT false,
            remitente_nombre TEXT,
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            actualizado_por TEXT
        )
        """
    )
    _rls("configuracion_canales")
    op.execute("ALTER TABLE modulo1.usuario ADD COLUMN telegram_chat_id TEXT")
    op.execute(
        """
        CREATE TABLE modulo1.notificacion_envio (
            envio_id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            job_id BIGINT NOT NULL,
            canal TEXT NOT NULL CHECK (canal IN ('mail', 'telegram', 'log')),
            destinatario TEXT NOT NULL,
            usuario_id UUID,
            estado TEXT NOT NULL CHECK (estado IN ('enviado', 'fallido')),
            proveedor_ref TEXT,
            error TEXT,
            intentos INTEGER NOT NULL DEFAULT 1,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_notificacion_envio UNIQUE (tenant_id, job_id, canal, destinatario)
        )
        """
    )
    _rls("notificacion_envio")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE modulo1.notificacion_envio_envio_id_seq TO modulo1_app")

    # --- paquete de entrega público ---------------------------------------------
    op.execute(
        """
        CREATE TABLE modulo1.paquete_entrega (
            paquete_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            token_hash TEXT NOT NULL UNIQUE,
            sujeto_id TEXT NOT NULL,
            creado_por TEXT NOT NULL,
            expira_en TIMESTAMPTZ NOT NULL,
            revocado_en TIMESTAMPTZ,
            accesos INTEGER NOT NULL DEFAULT 0,
            ultimo_acceso_en TIMESTAMPTZ,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_paquete_tenant_id UNIQUE (tenant_id, paquete_id),
            CONSTRAINT fk_paquete__sujeto_id FOREIGN KEY (tenant_id, sujeto_id) REFERENCES modulo1.legajo (tenant_id, sujeto_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_paquete_entrega_sujeto ON modulo1.paquete_entrega (tenant_id, sujeto_id)")
    op.execute("ALTER TABLE modulo1.paquete_entrega ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.paquete_entrega FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY paquete_entrega_aislamiento ON modulo1.paquete_entrega {_POLICY}")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON modulo1.paquete_entrega TO modulo1_app")
    # El endpoint público resuelve el tenant por token ANTES de abrir la sesión del tenant:
    # tabla lateral sin RLS (token_hash → tenant_id) mantenida por un trigger SECURITY
    # DEFINER y leída por una función SECURITY DEFINER — mismo patrón que tenant_slug (0003).
    op.execute("CREATE TABLE modulo1.paquete_token (token_hash TEXT PRIMARY KEY, tenant_id UUID NOT NULL)")
    op.execute(
        """
        CREATE FUNCTION modulo1.sincronizar_paquete_token() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, modulo1 AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                DELETE FROM modulo1.paquete_token WHERE token_hash = OLD.token_hash;
                RETURN OLD;
            END IF;
            INSERT INTO modulo1.paquete_token (token_hash, tenant_id) VALUES (NEW.token_hash, NEW.tenant_id) ON CONFLICT DO NOTHING;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION modulo1.sincronizar_paquete_token() FROM PUBLIC")
    op.execute("CREATE TRIGGER trg_paquete_token AFTER INSERT OR DELETE ON modulo1.paquete_entrega FOR EACH ROW EXECUTE FUNCTION modulo1.sincronizar_paquete_token()")
    op.execute(
        """
        CREATE FUNCTION modulo1.resolver_tenant_por_paquete(p_token_hash TEXT) RETURNS UUID
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = pg_catalog, modulo1 AS $$
            SELECT tenant_id FROM modulo1.paquete_token WHERE token_hash = p_token_hash
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION modulo1.resolver_tenant_por_paquete(TEXT) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION modulo1.resolver_tenant_por_paquete(TEXT) TO modulo1_app")
    op.execute(
        """
        CREATE TABLE modulo1.paquete_acceso (
            acceso_id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            paquete_id UUID NOT NULL,
            accedido_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            origen_hash TEXT,
            CONSTRAINT fk_paquete_acceso__paquete_id FOREIGN KEY (tenant_id, paquete_id) REFERENCES modulo1.paquete_entrega (tenant_id, paquete_id)
        )
        """
    )
    _rls("paquete_acceso")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE modulo1.paquete_acceso_acceso_id_seq TO modulo1_app")

    # --- score documental --------------------------------------------------------
    op.execute(
        """
        CREATE TABLE modulo1.score_snapshot (
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            fecha DATE NOT NULL,
            score NUMERIC(5,2) NOT NULL,
            exigidos INTEGER NOT NULL,
            cubiertos INTEGER NOT NULL,
            detalle JSONB NOT NULL,
            calculado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, fecha)
        )
        """
    )
    _rls("score_snapshot")

    # --- Drive -------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE modulo1.configuracion_drive (
            tenant_id UUID PRIMARY KEY REFERENCES modulo1.tenant(tenant_id),
            habilitado BOOLEAN NOT NULL DEFAULT false,
            carpeta_id TEXT,
            intervalo_horas INTEGER CHECK (intervalo_horas IS NULL OR intervalo_horas BETWEEN 1 AND 168),
            ultimo_escaneo_en TIMESTAMPTZ,
            ultimo_escaneo_resultado JSONB,
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            actualizado_por TEXT
        )
        """
    )
    _rls("configuracion_drive")
    op.execute(
        """
        CREATE TABLE modulo1.archivo_drive (
            archivo_drive_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            id_externo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            mime TEXT,
            modificado_externo TIMESTAMPTZ,
            hash_externo TEXT,
            visto_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            estado TEXT NOT NULL CHECK (estado IN ('importado', 'pendiente_revision', 'descartado')),
            confianza TEXT NOT NULL CHECK (confianza IN ('alta', 'media', 'baja')),
            extraccion JSONB NOT NULL,
            motivo TEXT,
            documento_id UUID,
            resuelto_por TEXT,
            resuelto_en TIMESTAMPTZ,
            CONSTRAINT uq_archivo_drive_externo UNIQUE (tenant_id, id_externo, hash_externo),
            CONSTRAINT fk_archivo_drive__documento_id FOREIGN KEY (tenant_id, documento_id) REFERENCES modulo1.documento (tenant_id, documento_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_archivo_drive_bandeja ON modulo1.archivo_drive (tenant_id, estado, visto_en)")
    _rls("archivo_drive")


def downgrade() -> None:
    for tabla in ("archivo_drive", "configuracion_drive", "score_snapshot", "paquete_acceso"):
        op.execute(f"DROP TABLE IF EXISTS modulo1.{tabla}")
    op.execute("DROP FUNCTION IF EXISTS modulo1.resolver_tenant_por_paquete(TEXT)")
    op.execute("DROP TABLE IF EXISTS modulo1.paquete_token")
    op.execute("DROP FUNCTION IF EXISTS modulo1.sincronizar_paquete_token() CASCADE")
    for tabla in ("paquete_entrega", "notificacion_envio", "configuracion_canales"):
        op.execute(f"DROP TABLE IF EXISTS modulo1.{tabla}")
    op.execute("ALTER TABLE modulo1.usuario DROP COLUMN IF EXISTS telegram_chat_id")
