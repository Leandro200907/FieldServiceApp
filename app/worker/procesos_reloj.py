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
from typing import Any, Callable

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


# --- 3. retención de archivos (A-05: dos fases, nunca "archivo borrado, base sin enterarse")
def control_retencion(
    tenant_id: str, storage: Storage, ahora_utc: datetime, abrir_sesion: Callable[[str], Any] | None = None
) -> dict[str, int]:
    """Purga el archivo físico de documentos no vigentes cuyo plazo de retención (por
    definición de requisito) ya pasó. Maneja sus propias transacciones porque el borrado
    físico NO puede ir dentro de una transacción SQL (4.4 de no-funcionales + A-05):

      fase 1 (tx)  candidatos `confirmado` con plazo vencido → `purga_pendiente`. Commit.
      fase 2       por cada `purga_pendiente`: borrado físico FUERA de toda transacción;
                   si `storage.borrar` confirma (o el archivo ya no existe) → (tx) clave
                   NULL, `purgado`, evento ArchivoPurgado. Commit por documento.
                   Si no confirma, queda `purga_pendiente` y se reintenta en la vuelta
                   siguiente — idempotente por construcción.

    Un corte entre borrar y confirmar deja `purga_pendiente` con archivo ausente: la
    vuelta siguiente lo detecta (`existe() == False`) y cierra la fase 2. La base nunca
    apunta a un archivo inexistente como si estuviera `confirmado`."""
    abrir = abrir_sesion or _sesion_por_defecto
    with abrir(tenant_id) as s:
        marcados = _marcar_purga_pendiente(s, ahora_utc)
    with abrir(tenant_id) as s:
        pendientes = s.execute(
            text("SELECT documento_id, clave_storage FROM modulo1.documento WHERE archivo_estado = 'purga_pendiente' "
                 "ORDER BY creado_en"),
        ).all()
    purgados = 0
    no_confirmados = 0
    for documento_id, clave in pendientes:
        try:
            borrado = bool(storage.borrar(clave))
        except Exception:
            log.exception("retención: error borrando %s", clave)
            borrado = False
        if not borrado:
            # Reconciliación: si el archivo ya no está (corte en una vuelta anterior), cerrar.
            try:
                borrado = not storage.existe(clave)
            except Exception:
                borrado = False
        if not borrado:
            no_confirmados += 1
            log.warning("retención: borrado NO confirmado para documento %s (%s); se reintenta", documento_id, clave)
            continue
        with abrir(tenant_id) as s:
            actualizado = s.execute(
                text(
                    "UPDATE modulo1.documento SET clave_storage = NULL, archivo_estado = 'purgado', "
                    "archivo_purgado_en = :ahora WHERE documento_id = :d AND archivo_estado = 'purga_pendiente'"
                ),
                {"d": documento_id, "ahora": ahora_utc},
            ).rowcount
            if actualizado:
                registrar_evento(
                    s, tenant_id, "ArchivoPurgado",
                    {"documento_id": str(documento_id), "clave_storage": clave, "purgado_en": ahora_utc.isoformat()},
                    usuario_id=None,
                )
                purgados += 1
    resumen = {"candidatos": marcados + len(pendientes), "marcados": marcados, "purgados": purgados,
               "no_confirmados": no_confirmados}
    with abrir(tenant_id) as s:
        latir(s, "control_retencion", tenant_id, True, resumen)
    return resumen


def _sesion_por_defecto(tenant_id: str):
    from app.db import tenant_session

    return tenant_session(tenant_id)


def _marcar_purga_pendiente(session: Session, ahora_utc: datetime) -> int:
    """Fase 1: decide qué purgar y lo deja escrito antes de tocar el filesystem."""
    return session.execute(
        text(
            """
            UPDATE modulo1.documento d SET archivo_estado = 'purga_pendiente'
            FROM modulo1.definicion_requisito r
            WHERE r.requisito_definicion_id = d.requisito_definicion_id
              AND d.estado_version IN :estados
              AND d.archivo_estado = 'confirmado'
              AND r.plazo_retencion_archivo IS NOT NULL
              AND d.creado_en + r.plazo_retencion_archivo < :ahora
            """
        ).bindparams(bindparam("estados", expanding=True)),
        {"estados": list(ESTADOS_NO_VIGENTES), "ahora": ahora_utc},
    ).rowcount
