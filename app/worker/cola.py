"""Cola nativa Postgres sobre `modulo1.job_queue` (8.5).

`SELECT ... FOR UPDATE SKIP LOCKED` con lease obligatorio: un job tomado queda
`en_curso` hasta `lease_hasta`; si el worker muere, pasado el lease cualquier otro lo
puede retomar. No existe `tomar` sin lease.

Colas válidas (CHECK en la tabla): drenaje_outbox, notificaciones, evidencia_qr,
score_documental, validacion_evidencia.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

COLAS = ("drenaje_outbox", "notificaciones", "evidencia_qr", "score_documental", "validacion_evidencia")


@dataclass(frozen=True)
class Job:
    id: int
    tenant_id: str | None
    cola: str
    payload: dict[str, Any]
    intentos: int
    lease_hasta: datetime | None
    estado: str


def _fila_a_job(fila) -> Job:
    return Job(
        id=fila.id,
        tenant_id=str(fila.tenant_id) if fila.tenant_id else None,
        cola=fila.cola,
        payload=fila.payload if isinstance(fila.payload, dict) else json.loads(fila.payload),
        intentos=fila.intentos,
        lease_hasta=fila.lease_hasta,
        estado=fila.estado,
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
    """Toma el próximo job disponible de la cola con un lease de `lease_seg` segundos.
    Pendientes, o en_curso con lease vencido (worker caído). SKIP LOCKED: dos workers
    concurrentes nunca reciben el mismo job."""
    if lease_seg <= 0:
        raise ValueError("lease_seg debe ser positivo: el lease es obligatorio")
    fila = session.execute(
        text(
            """
            UPDATE modulo1.job_queue
            SET estado = 'en_curso', tomado_en = now(),
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
            RETURNING id, tenant_id, cola, payload, intentos, lease_hasta, estado
            """
        ),
        {"c": cola, "lease": lease_seg},
    ).first()
    return _fila_a_job(fila) if fila else None


def completar(session: Session, id: int) -> None:
    session.execute(
        text("UPDATE modulo1.job_queue SET estado = 'completado', lease_hasta = NULL WHERE id = :id"), {"id": id}
    )


def fallar(session: Session, id: int, reintentar_en_seg: int | None = None, max_intentos: int = 5) -> str:
    """Marca el intento como fallido. Si ya se agotaron los intentos pasa a `fallido`
    (terminal); si no, vuelve a `pendiente` con backoff exponencial (o el que se pida).
    Devuelve el estado resultante."""
    fila = session.execute(text("SELECT intentos FROM modulo1.job_queue WHERE id = :id FOR UPDATE"), {"id": id}).first()
    if fila is None:
        raise ValueError(f"job {id} inexistente")
    intentos = int(fila[0])
    if intentos >= max_intentos:
        session.execute(
            text("UPDATE modulo1.job_queue SET estado = 'fallido', lease_hasta = NULL WHERE id = :id"), {"id": id}
        )
        return "fallido"
    espera = reintentar_en_seg if reintentar_en_seg is not None else min(30 * (2 ** max(intentos - 1, 0)), 3600)
    session.execute(
        text(
            "UPDATE modulo1.job_queue SET estado = 'pendiente', lease_hasta = NULL, "
            "disponible_en = now() + make_interval(secs => :e) WHERE id = :id"
        ),
        {"e": espera, "id": id},
    )
    return "pendiente"
