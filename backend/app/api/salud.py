"""Salud y diagnóstico (cierre operativo).

- `GET /v1/salud/vivo`  — liveness: el proceso responde. Siempre 200, sin tocar nada.
- `GET /v1/salud/listo` — readiness: base accesible con el rol de aplicación, migración
  aplicada == `app.version.MIGRACION_HEAD`, storage disponible y worker vivo (último
  latido global `latido_proceso(nombre='worker', tenant NULL).ultimo_ok` más reciente que
  `WORKER_LATIDO_MAX_SEG`). 200 si todo está `ok`, 503 si no. La respuesta sólo dice qué
  chequeo falló con un código cerrado (`ok`, `no_disponible`, `atrasada`, `adelantada`,
  `desconocida`, `sin_latido`, `vencido`): nunca DSN, rutas, hostname, PID, excepciones
  ni secretos. Ninguna de las dos rutas exige JWT.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.comun.reloj import ahora_utc
from app.config import settings
from app.db import platform_session
from app.storage import obtener_storage
from app.version import MIGRACION_HEAD, VERSION

log = logging.getLogger("modulo1.salud")
router = APIRouter(prefix="/salud", tags=["salud"])


class VivoResponse(BaseModel):
    ok: bool
    version: str


@router.get("/vivo", response_model=VivoResponse)
def vivo() -> VivoResponse:
    return VivoResponse(ok=True, version=VERSION)


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


def _chequeo_worker(ahora: datetime | None = None, umbral_seg: int | None = None) -> str:
    """`ok` si el latido global del worker es más reciente que el umbral; `sin_latido` si
    nunca latió; `vencido` si envejeció; `no_disponible` si no se puede consultar."""
    instante = ahora or ahora_utc()
    umbral = settings.worker_latido_max_seg if umbral_seg is None else umbral_seg
    try:
        with platform_session() as s:
            ultimo = s.execute(text(
                "SELECT ultimo_ok FROM modulo1.latido_proceso WHERE nombre = 'worker' AND tenant_id IS NULL"
            )).scalar()
    except Exception as e:  # noqa: BLE001
        log.warning("readiness: latido del worker no disponible (%s)", type(e).__name__)
        return "no_disponible"
    if ultimo is None:
        return "sin_latido"
    if ultimo < instante - timedelta(seconds=umbral):
        log.warning("readiness: latido del worker vencido (último hace %ss, umbral %ss)", int((instante - ultimo).total_seconds()), umbral)
        return "vencido"
    return "ok"


def _chequeo_storage() -> str:
    try:
        return "ok" if obtener_storage().disponible() else "no_disponible"
    except Exception as e:  # noqa: BLE001
        log.warning("readiness: storage no disponible (%s)", type(e).__name__)
        return "no_disponible"


@router.get("/listo")
def listo() -> JSONResponse:
    db, migracion = _chequeo_db()
    chequeos = {"db": db, "migracion": migracion, "storage": _chequeo_storage(), "worker": _chequeo_worker()}
    ok = all(v == "ok" for v in chequeos.values())
    return JSONResponse(status_code=200 if ok else 503, content={"ok": ok, "version": VERSION, "chequeos": chequeos})
