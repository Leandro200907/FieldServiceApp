"""Cola nativa Postgres sobre `modulo1.job_queue` (8.5) con leases con PROPIETARIO (A-06).

`SELECT ... FOR UPDATE SKIP LOCKED` con lease obligatorio: un job tomado queda `en_curso`
hasta `lease_hasta` con un `lease_token` nuevo en cada adquisición. Si el worker muere,
pasado el lease cualquier otro lo puede retomar — y desde ese momento el token anterior
deja de servir: `completar`, `fallar` y `renovar_lease` hacen
`UPDATE … WHERE estado='en_curso' AND lease_token = :token RETURNING` y exigen exactamente
una fila. No se confía en el id del worker: solo en el token.

Colas válidas (CHECK en la tabla): drenaje_outbox, notificaciones, evidencia_qr,
score_documental, validacion_evidencia.

RESTRICCIÓN PARA HANDLERS (fencing, A-06): `procesar_cola` ejecuta el handler y el
`completar` en la MISMA transacción; si el lease se perdió, todo se revierte. Por eso:
  - los handlers pueden hacer escrituras transaccionales en PostgreSQL con libertad;
  - NO deben hacer I/O externo irreversible (correo, HTTP, borrado físico, etc.) antes de
    que el lease se valide y la transacción confirme: el rollback no puede deshacerlo;
  - todo efecto externo sale por outbox (`app.comun.eventos.encolar_outbox`) o por un
    paso idempotente en dos fases (como la purga de archivos, `control_retencion`), y el
    consumidor externo debe ser idempotente.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

COLAS = ("drenaje_outbox", "notificaciones", "evidencia_qr", "score_documental", "validacion_evidencia")


class LeaseAjeno(Exception):
    """El job no está `en_curso` a nombre de este token (venció y otro lo retomó, ya se
    completó, o el token es incorrecto). El llamador no debe tocar nada más."""


@dataclass(frozen=True)
class Job:
    id: int
    tenant_id: str | None
    cola: str
    payload: dict[str, Any]
    intentos: int
    lease_hasta: datetime | None
    estado: str
    lease_token: uuid.UUID | None


def _fila_a_job(fila) -> Job:
    return Job(
        id=fila.id,
        tenant_id=str(fila.tenant_id) if fila.tenant_id else None,
        cola=fila.cola,
        payload=fila.payload if isinstance(fila.payload, dict) else json.loads(fila.payload),
        intentos=fila.intentos,
        lease_hasta=fila.lease_hasta,
        estado=fila.estado,
        lease_token=fila.lease_token,
    )


def encolar(
    session: Session,
    cola: str,
    payload: dict[str, Any],
    tenant_id: str | None = None,
    disponible_en: datetime | None = None,
) -> int:
    if cola not in COLAS:
        raise ValueError(f"cola desconocida: {cola} (válidas: {COLAS})")
    fila = session.execute(
        text(
            "INSERT INTO modulo1.job_queue (tenant_id, cola, payload, disponible_en) "
            "VALUES (:t, :c, CAST(:p AS jsonb), COALESCE(:d, now())) RETURNING id"
        ),
        {"t": tenant_id, "c": cola, "p": json.dumps(payload, default=str, ensure_ascii=False), "d": disponible_en},
    ).first()
    return int(fila[0])


def tomar(session: Session, cola: str, lease_seg: int = 60) -> Job | None:
    """Toma el próximo job disponible de la cola con un lease de `lease_seg` segundos y un
    `lease_token` nuevo. Pendientes, o en_curso con lease vencido (worker caído). SKIP
    LOCKED: dos workers concurrentes nunca reciben el mismo job."""
    if lease_seg <= 0:
        raise ValueError("lease_seg debe ser positivo: el lease es obligatorio")
    token = uuid.uuid4()
    fila = session.execute(
        text(
            """
            UPDATE modulo1.job_queue
            SET estado = 'en_curso', tomado_en = now(), lease_token = :token,
                lease_hasta = now() + make_interval(secs => :lease), intentos = intentos + 1
            WHERE id = (
                SELECT id FROM modulo1.job_queue
                WHERE cola = :c
                  AND (estado = 'pendiente' OR (estado = 'en_curso' AND lease_hasta < now()))
                  AND disponible_en <= now()
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id, tenant_id, cola, payload, intentos, lease_hasta, estado, lease_token
            """
        ),
        {"c": cola, "lease": lease_seg, "token": token},
    ).first()
    return _fila_a_job(fila) if fila else None


def _exigir_una_fila(afectadas: int, id: int, accion: str) -> None:
    if afectadas != 1:
        raise LeaseAjeno(f"job {id}: no se pudo {accion} — el lease no pertenece a este token o el job ya no está en curso")


def completar(session: Session, id: int, lease_token: uuid.UUID) -> None:
    afectadas = session.execute(
        text(
            "UPDATE modulo1.job_queue SET estado = 'completado', lease_hasta = NULL, lease_token = NULL "
            "WHERE id = :id AND estado = 'en_curso' AND lease_token = :token RETURNING id"
        ),
        {"id": id, "token": lease_token},
    ).rowcount
    _exigir_una_fila(afectadas, id, "completar")


def renovar_lease(session: Session, id: int, lease_token: uuid.UUID, lease_seg: int) -> None:
    """Extiende el lease de un job en curso; solo su propietario y solo si no venció (un
    lease vencido pudo ser readquirido: hay que volver a tomar)."""
    if lease_seg <= 0:
        raise ValueError("lease_seg debe ser positivo")
    afectadas = session.execute(
        text(
            "UPDATE modulo1.job_queue SET lease_hasta = now() + make_interval(secs => :lease) "
            "WHERE id = :id AND estado = 'en_curso' AND lease_token = :token AND lease_hasta >= now() RETURNING id"
        ),
        {"id": id, "token": lease_token, "lease": lease_seg},
    ).rowcount
    _exigir_una_fila(afectadas, id, "renovar el lease")


def fallar(
    session: Session, id: int, lease_token: uuid.UUID, reintentar_en_seg: int | None = None, max_intentos: int = 5
) -> str:
    """Marca el intento como fallido (solo el propietario del lease). Si ya se agotaron
    los intentos pasa a `fallido` (terminal); si no, vuelve a `pendiente` con backoff
    exponencial (o el que se pida). Devuelve el estado resultante."""
    fila = session.execute(
        text("SELECT intentos FROM modulo1.job_queue WHERE id = :id AND estado = 'en_curso' AND lease_token = :token FOR UPDATE"),
        {"id": id, "token": lease_token},
    ).first()
    if fila is None:
        raise LeaseAjeno(f"job {id}: no se pudo fallar — el lease no pertenece a este token o el job ya no está en curso")
    intentos = int(fila[0])
    if intentos >= max_intentos:
        afectadas = session.execute(
            text(
                "UPDATE modulo1.job_queue SET estado = 'fallido', lease_hasta = NULL, lease_token = NULL "
                "WHERE id = :id AND estado = 'en_curso' AND lease_token = :token RETURNING id"
            ),
            {"id": id, "token": lease_token},
        ).rowcount
        _exigir_una_fila(afectadas, id, "marcar fallido")
        return "fallido"
    espera = reintentar_en_seg if reintentar_en_seg is not None else min(30 * (2 ** max(intentos - 1, 0)), 3600)
    afectadas = session.execute(
        text(
            "UPDATE modulo1.job_queue SET estado = 'pendiente', lease_hasta = NULL, lease_token = NULL, "
            "disponible_en = now() + make_interval(secs => :e) "
            "WHERE id = :id AND estado = 'en_curso' AND lease_token = :token RETURNING id"
        ),
        {"e": espera, "id": id, "token": lease_token},
    ).rowcount
    _exigir_una_fila(afectadas, id, "reprogramar")
    return "pendiente"
