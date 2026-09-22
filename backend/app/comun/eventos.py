"""Eventos internos (event_log, síncronos) y hacia Módulo 2 (outbox) — 8.3 / A-07.

- `registrar_evento`: log directo en la misma transacción de negocio y DESPACHO de la
  política de revaluación (tabla 7.2) para los eventos fuente declarados en
  `app.core.revaluacion.EVENTOS_FUENTE` — nada más pasa por ella. Devuelve el `evento_id`
  (identidad inmutable del evento causal, UNIQUE por tenant).
- `registrar_evento_interno`: mismo registro, SIN despacho. Es la vía obligatoria para
  los eventos que la propia política produce (`AvisoDeRevaluacionAbierto/Cerrado`,
  `CumplimientoEmpresaAfectado/Regularizado`): abrir o cerrar un aviso nunca vuelve a
  disparar la política.
- `encolar_outbox`: SOLO para los dos eventos que cruzan a Módulo 2, en la misma
  transacción, con `clave_dedup` (UNIQUE por tenant, `ON CONFLICT DO NOTHING`) y
  `version_contrato`. Lo publica el worker, nunca este módulo.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

EVENTOS_OUTBOX = {"HabilitacionRequiereRevaluacion", "CumplimientoEmpresaAfectado"}
VERSION_CONTRATO = "1.0"


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)


def _insertar(session: Session, tenant_id: str, tipo: str, payload: dict[str, Any], usuario_id: str | None) -> str:
    datos = dict(payload)
    datos["usuario_id"] = usuario_id or "sistema"
    fila = session.execute(
        text(
            "INSERT INTO modulo1.event_log (tenant_id, tipo, payload) VALUES (:t, :tipo, CAST(:p AS jsonb)) "
            "RETURNING evento_id"
        ),
        {"t": tenant_id, "tipo": tipo, "p": _json(datos)},
    ).first()
    return str(fila[0])


def registrar_evento_interno(
    session: Session, tenant_id: str, tipo: str, payload: dict[str, Any], usuario_id: str | None
) -> str:
    """Registro sin despacho de la política (ver docstring del módulo)."""
    return _insertar(session, tenant_id, tipo, payload, usuario_id)


def registrar_evento(
    session: Session, tenant_id: str, tipo: str, payload: dict[str, Any], usuario_id: str | None
) -> str:
    evento_id = _insertar(session, tenant_id, tipo, payload, usuario_id)
    # Import perezoso: revaluacion importa este módulo; el mapa cerrado vive allá.
    from app.core.revaluacion import EVENTOS_FUENTE, aplicar_politica

    if tipo in EVENTOS_FUENTE:
        aplicar_politica(session, tenant_id, evento_id, tipo, payload)
    return evento_id


def encolar_outbox(
    session: Session, tenant_id: str, tipo: str, payload: dict[str, Any], clave_dedup: str | None = None,
    disponible_en: datetime | None = None,
) -> bool:
    """True si se insertó; False si `clave_dedup` ya existía (replay idempotente).
    `disponible_en=None` → `now()` de la base (comportamiento normal); un valor explícito
    es para reloj controlado (tests, reproceso) — igual que `encolar()` de `job_queue`."""
    if tipo not in EVENTOS_OUTBOX:
        raise ValueError(f"{tipo} no es un evento de outbox (solo {sorted(EVENTOS_OUTBOX)})")
    datos = {"version_contrato": VERSION_CONTRATO, "tenant_id": str(tenant_id), **payload}
    fila = session.execute(
        text(
            "INSERT INTO modulo1.outbox_events (tenant_id, tipo, payload, clave_dedup, version_contrato, disponible_en) "
            "VALUES (:t, :tipo, CAST(:p AS jsonb), :k, :v, COALESCE(:d, now())) "
            "ON CONFLICT (tenant_id, clave_dedup) DO NOTHING RETURNING evento_id"
        ),
        {"t": tenant_id, "tipo": tipo, "p": _json(datos), "k": clave_dedup, "v": VERSION_CONTRATO, "d": disponible_en},
    ).first()
    return fila is not None
