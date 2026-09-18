"""Drenaje del transactional outbox hacia Módulo 2 (8.3).

Los comandos escriben en `outbox_events` en su misma transacción; este módulo los
publica por polling y marca `procesado_en`. `Publicador` es el puerto de salida: hoy
`PublicadorEnLog` (dev) y `PublicadorEnMemoria` (tests); el transporte real a Módulo 2
se enchufa implementando el Protocol, sin tocar el drenaje.

At-least-once: si `publicar` falla, el evento queda sin `procesado_en` con `intentos+1`
y se reintenta en la próxima vuelta. El consumidor deduplica por `evento_id`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("modulo1.worker.outbox")


class Publicador(Protocol):
    def publicar(self, tipo: str, payload: dict[str, Any], evento_id: str) -> None: ...


class PublicadorEnLog:
    def publicar(self, tipo: str, payload: dict[str, Any], evento_id: str) -> None:
        log.info("outbox -> modulo2 %s %s %s", tipo, evento_id, payload)


@dataclass
class PublicadorEnMemoria:
    eventos: list[tuple[str, dict[str, Any], str]] = field(default_factory=list)
    fallar_con: Exception | None = None

    def publicar(self, tipo: str, payload: dict[str, Any], evento_id: str) -> None:
        if self.fallar_con is not None:
            raise self.fallar_con
        self.eventos.append((tipo, payload, evento_id))


def drenar_outbox(session: Session, tenant_id: str, publicador: Publicador, lote: int = 100) -> int:
    """Publica hasta `lote` eventos pendientes del tenant en sesión. Devuelve cuántos
    quedaron marcados como procesados."""
    filas = session.execute(
        text(
            """
            SELECT evento_id, tipo, payload FROM modulo1.outbox_events
            WHERE procesado_en IS NULL AND tenant_id = :t
            ORDER BY creado_en, evento_id
            FOR UPDATE SKIP LOCKED
            LIMIT :n
            """
        ),
        {"t": tenant_id, "n": lote},
    ).all()
    publicados = 0
    for evento_id, tipo, payload in filas:
        try:
            publicador.publicar(tipo, dict(payload), str(evento_id))
        except Exception:
            log.exception("outbox: falló publicar %s %s", tipo, evento_id)
            session.execute(
                text("UPDATE modulo1.outbox_events SET intentos = intentos + 1 WHERE evento_id = :e"),
                {"e": evento_id},
            )
            continue
        session.execute(
            text("UPDATE modulo1.outbox_events SET procesado_en = now(), intentos = intentos + 1 WHERE evento_id = :e"),
            {"e": evento_id},
        )
        publicados += 1
    return publicados
