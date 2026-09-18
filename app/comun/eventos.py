"""Eventos internos (event_log, síncronos) y hacia Módulo 2 (outbox) — 8.3.

- `registrar_evento`: log directo en la misma transacción de negocio. Todo evento
  originado por un comando de usuario lleva `usuario_id` (3.1 de no-funcionales); los
  de sistema llevan usuario_id="sistema".
- `encolar_outbox`: SOLO para los dos eventos que cruzan a Módulo 2. Se escribe en la
  misma transacción; lo publica el worker (app/worker), nunca este módulo.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

EVENTOS_OUTBOX = {"HabilitacionRequiereRevaluacion", "CumplimientoEmpresaAfectado"}


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)


def registrar_evento(
    session: Session, tenant_id: str, tipo: str, payload: dict[str, Any], usuario_id: str | None
) -> None:
    datos = dict(payload)
    datos["usuario_id"] = usuario_id or "sistema"
    session.execute(
        text("INSERT INTO modulo1.event_log (tenant_id, tipo, payload) VALUES (:t, :tipo, CAST(:p AS jsonb))"),
        {"t": tenant_id, "tipo": tipo, "p": _json(datos)},
    )


def encolar_outbox(session: Session, tenant_id: str, tipo: str, payload: dict[str, Any]) -> None:
    if tipo not in EVENTOS_OUTBOX:
        raise ValueError(f"{tipo} no es un evento de outbox (solo {sorted(EVENTOS_OUTBOX)})")
    session.execute(
        text("INSERT INTO modulo1.outbox_events (tenant_id, tipo, payload) VALUES (:t, :tipo, CAST(:p AS jsonb))"),
        {"t": tenant_id, "tipo": tipo, "p": _json(payload)},
    )
