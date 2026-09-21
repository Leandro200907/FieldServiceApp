"""Drenaje del transactional outbox hacia Módulo 2 (8.3).

Los comandos escriben en `outbox_events` en su misma transacción; este módulo los
publica por polling y marca `procesado_en`. `Publicador` es el puerto de salida: hoy
`PublicadorEnLog` (dev) y `PublicadorEnMemoria` (tests); el transporte real a Módulo 2
se enchufa implementando el Protocol, sin tocar el drenaje.

At-least-once: si `publicar` falla, el evento queda sin `procesado_en`, con `intentos+1` y
`disponible_en` corrido por backoff exponencial. El consumidor deduplica por `evento_id`.

Política de la cola crítica (arquitectura-tecnica.md §8.4: *"una falla persistente acá
significa que Módulo 2 nunca se entera de un cambio de cumplimiento... lleva más
reintentos/mayor duración y una alerta obligatoria al agotarse — nunca dead-letter
silencioso"*), más reintentos y más duración que `job_queue` (`MAX_INTENTOS`/`backoff_seg`
de `app/worker/cola.py`, pensados para colas best-effort): tope de backoff de 6 horas,
hasta `MAX_INTENTOS_OUTBOX` intentos. Al agotarse, la fila NUNCA desaparece ni se calla:
queda `estancado_en` (no se vuelve a tomar sola) y se encola, en la MISMA transacción, una
notificación a `configuracion` — la alerta obligatoria, no una opción. `reprocesar()` es el
único camino para que un evento estancado vuelva a intentarse (uso: después de confirmar
que la causa de fondo ya se resolvió — Módulo 2 recuperado, contrato corregido)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.comun.reloj import ahora_utc
from app.worker.cola import sanear_error

log = logging.getLogger("modulo1.worker.outbox")

MAX_INTENTOS_OUTBOX = 20
BACKOFF_BASE_SEG = 30
BACKOFF_TOPE_SEG = 6 * 3600


def backoff_outbox_seg(intentos: int) -> int:
    return min(BACKOFF_BASE_SEG * (2 ** max(intentos - 1, 0)), BACKOFF_TOPE_SEG)


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


def _alertar_estancado(session: Session, tenant_id: str, evento_id: str, tipo: str, intentos: int, error: str | None) -> None:
    from app.worker.cola import encolar

    encolar(session, "notificaciones", {
        "tipo": "OutboxEstancado", "destinatario_rol": "configuracion",
        "evento_id": str(evento_id), "evento_tipo": tipo, "intentos": intentos, "error": error,
    }, tenant_id=tenant_id, disponible_en=ahora_utc())
    log.error("outbox: evento %s (%s) ESTANCADO tras %s intentos — %s", evento_id, tipo, intentos, error)


def drenar_outbox(session: Session, tenant_id: str, publicador: Publicador, lote: int = 100, ahora: datetime | None = None) -> int:
    """Publica hasta `lote` eventos pendientes y disponibles (backoff vencido, no
    estancados) del tenant en sesión. Devuelve cuántos quedaron marcados como
    procesados (no cuenta fallidos ni estancados — para eso ver `estancados_de`)."""
    ahora = ahora or ahora_utc()
    filas = session.execute(
        text(
            """
            SELECT evento_id, tipo, payload, intentos FROM modulo1.outbox_events
            WHERE procesado_en IS NULL AND estancado_en IS NULL AND tenant_id = :t AND disponible_en <= :ahora
            ORDER BY creado_en, evento_id
            FOR UPDATE SKIP LOCKED
            LIMIT :n
            """
        ),
        {"t": tenant_id, "ahora": ahora, "n": lote},
    ).all()
    publicados = 0
    for evento_id, tipo, payload, intentos in filas:
        try:
            publicador.publicar(tipo, dict(payload), str(evento_id))
        except Exception as exc:
            error = sanear_error(exc)
            nuevos_intentos = intentos + 1
            log.warning("outbox: falló publicar %s %s (intento %s) — %s", tipo, evento_id, nuevos_intentos, error)
            if nuevos_intentos >= MAX_INTENTOS_OUTBOX:
                session.execute(
                    text("UPDATE modulo1.outbox_events SET intentos = :i, ultimo_error = :e, estancado_en = :ahora WHERE evento_id = :ev"),
                    {"i": nuevos_intentos, "e": error, "ahora": ahora, "ev": evento_id},
                )
                _alertar_estancado(session, tenant_id, str(evento_id), tipo, nuevos_intentos, error)
            else:
                disponible_en = ahora + timedelta(seconds=backoff_outbox_seg(nuevos_intentos))
                session.execute(
                    text("UPDATE modulo1.outbox_events SET intentos = :i, ultimo_error = :e, disponible_en = :d WHERE evento_id = :ev"),
                    {"i": nuevos_intentos, "e": error, "d": disponible_en, "ev": evento_id},
                )
            continue
        session.execute(
            text("UPDATE modulo1.outbox_events SET procesado_en = :ahora, intentos = intentos + 1 WHERE evento_id = :e"),
            {"ahora": ahora, "e": evento_id},
        )
        publicados += 1
    return publicados


def estancados(session: Session, tenant_id: str) -> list[dict[str, Any]]:
    """Eventos que agotaron el tope de intentos: nunca desaparecen, quedan acá hasta que
    alguien los reprocese a mano."""
    filas = session.execute(text(
        "SELECT evento_id, tipo, payload, intentos, ultimo_error, estancado_en, creado_en FROM modulo1.outbox_events "
        "WHERE tenant_id = :t AND estancado_en IS NOT NULL ORDER BY estancado_en"), {"t": tenant_id}).mappings().all()
    return [dict(f) for f in filas]


def reprocesar(session: Session, tenant_id: str, evento_id: str | None = None, ahora: datetime | None = None) -> int:
    """Saca del estado estancado — un evento puntual, o todos los del tenant si no se
    pasa `evento_id` — y lo deja disponible para el próximo drenaje. Devuelve cuántos
    reactivó. Uso previsto: después de confirmar a mano que la causa de fondo (Módulo 2
    caído, contrato de payload incompatible) ya se resolvió — nunca automático."""
    ahora = ahora or ahora_utc()
    cond = "estancado_en IS NOT NULL AND tenant_id = :t"
    params: dict[str, Any] = {"t": tenant_id, "ahora": ahora}
    if evento_id is not None:
        cond += " AND evento_id = :e"
        params["e"] = evento_id
    filas = session.execute(text(
        f"UPDATE modulo1.outbox_events SET estancado_en = NULL, intentos = 0, disponible_en = :ahora, ultimo_error = NULL "
        f"WHERE {cond} RETURNING evento_id"), params).all()
    return len(filas)
