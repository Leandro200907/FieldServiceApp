"""Salud y diagnóstico (cierre operativo).

- `GET /v1/salud/vivo`  — liveness: el proceso responde. Siempre 200, sin tocar nada.
- `GET /v1/salud/listo` — readiness: base accesible con el rol de aplicación, migración
  aplicada == `app.version.MIGRACION_HEAD`, storage disponible. 200 si todo está `ok`,
  503 si no. La respuesta sólo dice qué chequeo falló con un código cerrado (`ok`,
  `no_disponible`, `atrasada`, `adelantada`): nunca DSN, rutas, excepciones ni secretos.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import platform_session
from app.storage import obtener_storage
from app.version import MIGRACION_HEAD, VERSION

log = logging.getLogger("modulo1.salud")
router = APIRouter(prefix="/salud", tags=["salud"])


@router.get("/vivo")
def vivo() -> dict:
    return {"ok": True, "version": VERSION}


def _chequeo_db() -> tuple[str, str]:
    """(db, migracion). Una sola consulta: si la base no responde, ambos fallan."""
    try:
        with platform_session() as s:
            aplicada = s.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as e:  # noqa: BLE001 — el detalle va al log, nunca al cliente
        log.warning("readiness: base no disponible (%s)", type(e).__name__)
        return "no_disponible", "desconocida"
    if aplicada == MIGRACION_HEAD:
        return "ok", "ok"
    log.warning("readiness: migración aplicada %s, esperada %s", aplicada, MIGRACION_HEAD)
    return "ok", "atrasada" if (aplicada or "") < MIGRACION_HEAD else "adelantada"


def _chequeo_storage() -> str:
    try:
        return "ok" if obtener_storage().disponible() else "no_disponible"
    except Exception as e:  # noqa: BLE001
        log.warning("readiness: storage no disponible (%s)", type(e).__name__)
        return "no_disponible"


@router.get("/listo")
def listo() -> JSONResponse:
    db, migracion = _chequeo_db()
    chequeos = {"db": db, "migracion": migracion, "storage": _chequeo_storage()}
    ok = all(v == "ok" for v in chequeos.values())
    return JSONResponse(status_code=200 if ok else 503, content={"ok": ok, "version": VERSION, "chequeos": chequeos})
