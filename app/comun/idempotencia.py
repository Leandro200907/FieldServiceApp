"""Idempotency-Key de transporte (8.2): header `Idempotency-Key` en POST /comandos/*.

Uso en un router:
    previo = buscar_resultado(session, tenant_id, clave)
    if previo is not None: return previo
    ... ejecutar comando ...
    guardar_resultado(session, tenant_id, clave, resultado)

Todo dentro de la misma tenant_session, así el registro de la clave y el efecto del
comando son atómicos. Para ImportarLote prevalece lote_id (lo maneja ese comando).
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

TTL_HORAS = 24


def buscar_resultado(session: Session, tenant_id: str, clave: str | None) -> dict[str, Any] | None:
    if not clave:
        return None
    fila = session.execute(
        text(
            "SELECT resultado FROM modulo1.idempotency_keys "
            "WHERE tenant_id = :t AND idempotency_key = :k AND expira_en > now() FOR UPDATE"
        ),
        {"t": tenant_id, "k": clave},
    ).first()
    return fila[0] if fila else None


def guardar_resultado(session: Session, tenant_id: str, clave: str | None, resultado: dict[str, Any]) -> None:
    if not clave:
        return
    session.execute(
        text(
            "INSERT INTO modulo1.idempotency_keys (tenant_id, idempotency_key, resultado, expira_en) "
            "VALUES (:t, :k, CAST(:r AS jsonb), now() + make_interval(hours => :h)) "
            "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING"
        ),
        {"t": tenant_id, "k": clave, "r": json.dumps(resultado, default=str), "h": TTL_HORAS},
    )
