"""Procesos de reloj (8.6): vencimientos, excepciones/constancias vencidas y retención.

Cada proceso recibe la sesión del tenant y `ahora_utc` (inyectado, nunca `now()` suelto:
"hoy" sale de `hoy_del_tenant`). Cada uno escribe su latido en `latido_proceso` al
terminar bien; el latido de error lo escribe `app/worker/main.py` en una sesión aparte
(la del proceso se revierte entera si falla).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.comun.eventos import encolar_outbox, registrar_evento
from app.comun.reloj import hoy_del_tenant
from app.storage.contrato import Storage
from app.worker.cola import encolar

log = logging.getLogger("modulo1.worker.reloj")

DIAS_AVISO_VENCIMIENTO = 30
ESTADOS_NO_VIGENTES = ("sucedida", "rechazada", "revertida_por_lote")
UUID_NULO = "00000000-0000-0000-0000-000000000000"


# --- latido -------------------------------------------------------------------------
def latir(session: Session, nombre: str, tenant_id: str | None, ok: bool, detalle: dict[str, Any] | None = None) -> None:
    """Upsert del latido de un proceso. `ok=True` actualiza `ultimo_ok`; `ok=False`
    actualiza `ultimo_error`. El detalle reemplaza al anterior."""
    session.execute(
        text(
            f"""
            INSERT INTO modulo1.latido_proceso (nombre, tenant_id, ultimo_ok, ultimo_error, detalle)
            VALUES (:n, :t, CASE WHEN :ok THEN now() END, CASE WHEN :ok THEN NULL ELSE now() END, CAST(:d AS jsonb))
            ON CONFLICT (nombre, (COALESCE(tenant_id, '{UUID_NULO}'::uuid))) DO UPDATE SET
                ultimo_ok = CASE WHEN EXCLUDED.ultimo_ok IS NOT NULL THEN EXCLUDED.ultimo_ok ELSE modulo1.latido_proceso.ultimo_ok END,
                ultimo_error = CASE WHEN EXCLUDED.ultimo_error IS NOT NULL THEN EXCLUDED.ultimo_error ELSE modulo1.latido_proceso.ultimo_error END,
                detalle = EXCLUDED.detalle,
                actualizado_en = now()
            """
        ),
        {"n": nombre, "t": tenant_id, "ok": ok, "d": json.dumps(detalle or {}, default=str, ensure_ascii=False)},
    )


# --- 1. control de vencimientos -----------------------------------------------------
def _alerta_ya_abierta(session: Session, documento_id: str) -> bool:
    """Hay una AlertaDeVencimientoAbierta para este id sin AlertaResuelta posterior."""
    fila = session.execute(
        text(
            """
            SELECT 1 FROM modulo1.event_log a
            WHERE a.tipo = 'AlertaDeVencimientoAbierta' AND a.payload->>'documento_id' = :d
              AND NOT EXISTS (
                  SELECT 1 FROM modulo1.event_log r
                  WHERE r.tipo = 'AlertaResuelta' AND r.payload->>'documento_id' = :d AND r.id > a.id)
            LIMIT 1
            """
        ),
        {"d": documento_id},
    ).first()
    return fila is not None


def _proximos_a_vencer(session: Session, limite: date) -> list[dict[str, Any]]:
    filas: list[dict[str, Any]] = []
    for tipo_objeto, sql in (
        (
            "documento",
            "SELECT documento_id AS id, sujeto_id, requisito_definicion_id, vigente_hasta FROM modulo1.documento "
            "WHERE estado_version = 'vigente' AND vigente_hasta <= :lim",
        ),
        (
            "acreditacion",
            "SELECT acreditacion_id AS id, persona_id AS sujeto_id, requisito_definicion_id, vigente_hasta "
            "FROM modulo1.acreditacion_competencia WHERE vigente_hasta <= :lim",
        ),
        (
            "induccion",
            "SELECT induccion_id AS id, persona_id AS sujeto_id, requisito_definicion_id, vigente_hasta "
            "FROM modulo1.induccion WHERE vigente_hasta <= :lim",
        ),
    ):
        for f in session.execute(text(sql), {"lim": limite}).mappings():
            filas.append({"tipo_objeto": tipo_objeto, **dict(f)})
    return filas


def control_vencimientos(session: Session, tenant_id: str, ahora_utc: datetime) -> dict[str, int]:
    """Abre (una sola vez) AlertaDeVencimientoAbierta para cada documento/acreditación/
    inducción que vence dentro de 30 días o ya venció, y encola la notificación."""
    hoy = hoy_del_tenant(session, tenant_id, ahora_utc)
    limite = hoy + timedelta(days=DIAS_AVISO_VENCIMIENTO)
    abiertas = 0
    revisadas = 0
    for fila in _proximos_a_vencer(session, limite):
        revisadas += 1
        objeto_id = str(fila["id"])
        if _alerta_ya_abierta(session, objeto_id):
            continue
        vigente_hasta: date = fila["vigente_hasta"]
        payload = {
            "documento_id": objeto_id,
            "tipo_objeto": fila["tipo_objeto"],
            "sujeto_id": fila["sujeto_id"],
            "requisito_definicion_id": str(fila["requisito_definicion_id"]) if fila["requisito_definicion_id"] else None,
            "vigente_hasta": vigente_hasta.isoformat(),
            "dias_restantes": (vigente_hasta - hoy).days,
            "vencido": vigente_hasta < hoy,
        }
        registrar_evento(session, tenant_id, "AlertaDeVencimientoAbierta", payload, usuario_id=None)
        encolar(session, "notificaciones", {"tipo": "AlertaDeVencimientoAbierta", **payload}, tenant_id=tenant_id)
        abiertas += 1
    resumen = {"revisadas": revisadas, "alertas_abiertas": abiertas, "hoy": hoy.isoformat()}
    latir(session, "control_vencimientos", tenant_id, True, resumen)
    return resumen


# --- 2. excepciones y constancias vencidas -------------------------------------------
def vencer_excepciones_y_constancias(session: Session, tenant_id: str, ahora_utc: datetime) -> dict[str, int]:
    hoy = hoy_del_tenant(session, tenant_id, ahora_utc)
    excepciones = session.execute(
        text(
            """
            UPDATE modulo1.excepcion SET estado = 'vencida'
            WHERE estado = 'otorgada' AND vigencia IS NOT NULL AND vigencia < :hoy
            RETURNING excepcion_id, sujeto_id, requisito_definicion_id, commitment_id, vigencia
            """
        ),
        {"hoy": hoy},
    ).all()
    for excepcion_id, sujeto_id, requisito_id, commitment_id, vigencia in excepciones:
        registrar_evento(
            session,
            tenant_id,
            "ExcepcionVencida",
            {
                "excepcion_id": str(excepcion_id),
                "sujeto_id": sujeto_id,
                "requisito_definicion_id": str(requisito_id),
                "commitment_id": commitment_id,
                "vigencia": vigencia.isoformat(),
            },
            usuario_id=None,
        )
        encolar_outbox(
            session,
            tenant_id,
            "HabilitacionRequiereRevaluacion",
            {"commitment_id": commitment_id, "motivo": "excepcion_vencida", "excepcion_id": str(excepcion_id), "sujeto_id": sujeto_id},
        )

    constancias = session.execute(
        text(
            """
            UPDATE modulo1.constancia_cliente SET estado = 'vencida'
            WHERE estado = 'vigente' AND vigencia IS NOT NULL AND vigencia < :hoy
            RETURNING constancia_id, sujeto_id, requisito_definicion_id, cliente_id, commitment_id, vigencia
            """
        ),
        {"hoy": hoy},
    ).all()
    for constancia_id, sujeto_id, requisito_id, cliente_id, commitment_id, vigencia in constancias:
        registrar_evento(
            session,
            tenant_id,
            "ConstanciaVencida",
            {
                "constancia_id": str(constancia_id),
                "sujeto_id": sujeto_id,
                "requisito_definicion_id": str(requisito_id),
                "cliente_id": str(cliente_id),
                "commitment_id": commitment_id,
                "vigencia": vigencia.isoformat(),
            },
            usuario_id=None,
        )
        # Constancia general (commitment_id NULL): Módulo 2 resuelve por sujeto+cliente.
        encolar_outbox(
            session,
            tenant_id,
            "HabilitacionRequiereRevaluacion",
            {
                "commitment_id": commitment_id,
                "motivo": "constancia_vencida",
                "constancia_id": str(constancia_id),
                "sujeto_id": sujeto_id,
                "cliente_id": str(cliente_id),
            },
        )
    resumen = {"excepciones_vencidas": len(excepciones), "constancias_vencidas": len(constancias), "hoy": hoy.isoformat()}
    latir(session, "vencer_excepciones_y_constancias", tenant_id, True, resumen)
    return resumen


# --- 3. retención de archivos ---------------------------------------------------------
def control_retencion(session: Session, tenant_id: str, storage: Storage, ahora_utc: datetime) -> dict[str, int]:
    """Purga el archivo físico de documentos no vigentes cuyo plazo de retención (por
    definición de requisito) ya pasó. `ArchivoPurgado` SOLO si `storage.borrar` confirmó."""
    candidatos = _candidatos_retencion(session, ahora_utc)
    purgados = 0
    no_confirmados = 0
    for documento_id, clave in candidatos:
        try:
            borrado = bool(storage.borrar(clave))
        except Exception:
            log.exception("retención: error borrando %s", clave)
            borrado = False
        if not borrado:
            no_confirmados += 1
            log.warning("retención: borrado NO confirmado para documento %s (%s); se reintenta", documento_id, clave)
            continue
        session.execute(
            text("UPDATE modulo1.documento SET clave_storage = NULL WHERE documento_id = :d"), {"d": documento_id}
        )
        registrar_evento(
            session,
            tenant_id,
            "ArchivoPurgado",
            {"documento_id": str(documento_id), "clave_storage": clave, "purgado_en": ahora_utc.isoformat()},
            usuario_id=None,
        )
        purgados += 1
    resumen = {"candidatos": len(candidatos), "purgados": purgados, "no_confirmados": no_confirmados}
    latir(session, "control_retencion", tenant_id, True, resumen)
    return resumen


def _candidatos_retencion(session: Session, ahora_utc: datetime) -> list[tuple[Any, str]]:
    return session.execute(
        text(
            """
            SELECT d.documento_id, d.clave_storage
            FROM modulo1.documento d
            JOIN modulo1.definicion_requisito r ON r.requisito_definicion_id = d.requisito_definicion_id
            WHERE d.estado_version IN :estados
              AND d.clave_storage IS NOT NULL
              AND r.plazo_retencion_archivo IS NOT NULL
              AND d.creado_en + r.plazo_retencion_archivo < :ahora
            ORDER BY d.creado_en
            FOR UPDATE OF d SKIP LOCKED
            """
        ).bindparams(bindparam("estados", expanding=True)),
        {"estados": list(ESTADOS_NO_VIGENTES), "ahora": ahora_utc},
    ).all()
