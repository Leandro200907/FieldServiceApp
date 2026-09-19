"""Loop del worker (8.5/8.6).

    .venv/Scripts/python -m app.worker.main --una-vuelta   # una pasada y sale (CLI/cron)
    .venv/Scripts/python -m app.worker.main                # polling cada WORKER_POLL_SEG (5)

Cada vuelta: por cada tenant (`modulo1.listar_tenants()`, SECURITY DEFINER) abre
`tenant_session` y (1) drena el outbox, (2) procesa las colas nombradas con el handler
registrado, (3) corre los procesos de reloj. Cada proceso deja latido; si uno falla, el
error se registra en `latido_proceso` en una sesión aparte y la vuelta sigue con el
resto — un tenant roto no frena a los demás.

Cada job se procesa en tres transacciones cortas (tomar / handler / completar-fallar)
para que una falla SQL dentro del handler no deshaga el `tomar` ni deje el job
`pendiente` sin contar el intento.
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.comun.reloj import ahora_utc
from app.db import platform_session, tenant_session
from app.storage.contrato import Storage
from app.worker import cola as cola_mod
from app.worker.cola import Job
from app.worker.outbox import Publicador, PublicadorEnLog, drenar_outbox
from app.worker.procesos_reloj import (
    control_retencion,
    control_vencimientos,
    latir,
    vencer_excepciones_y_constancias,
)

log = logging.getLogger("modulo1.worker")

Handler = Callable[[Session, Job, dict[str, Any]], None]
MAX_JOBS_POR_COLA_POR_VUELTA = 50
LEASE_SEG = 60


# --- handlers ---------------------------------------------------------------------
def handler_notificaciones(session: Session, job: Job, contexto: dict[str, Any]) -> None:
    # v1: sin canal de salida todavía; la notificación queda en el log.
    log.info("notificación tenant=%s %s", job.tenant_id, job.payload)


def handler_drenaje_outbox(session: Session, job: Job, contexto: dict[str, Any]) -> None:
    if job.tenant_id:
        drenar_outbox(session, job.tenant_id, contexto["publicador"])


def _stub(nombre: str) -> Handler:
    def handler(session: Session, job: Job, contexto: dict[str, Any]) -> None:
        log.info("cola %s: no implementado en v1 (job %s completado sin efecto)", nombre, job.id)

    return handler


HANDLERS: dict[str, Handler] = {
    "drenaje_outbox": handler_drenaje_outbox,
    "notificaciones": handler_notificaciones,
    "evidencia_qr": _stub("evidencia_qr"),
    "score_documental": _stub("score_documental"),
    "validacion_evidencia": _stub("validacion_evidencia"),
}


# --- infraestructura de la vuelta -------------------------------------------------
def listar_tenants() -> list[str]:
    with platform_session() as s:
        return [str(f[0]) for f in s.execute(text("SELECT * FROM modulo1.listar_tenants()")).all()]


def _latido_de_error(nombre: str, tenant_id: str | None, error: Exception) -> None:
    try:
        if tenant_id:
            with tenant_session(tenant_id) as s:
                latir(s, nombre, tenant_id, False, {"error": f"{type(error).__name__}: {error}"[:500]})
        else:
            with platform_session() as s:
                latir(s, nombre, None, False, {"error": f"{type(error).__name__}: {error}"[:500]})
    except Exception:
        log.exception("no se pudo registrar el latido de error de %s", nombre)


def _con_latido(nombre: str, tenant_id: str | None, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception as e:
        log.exception("proceso %s tenant=%s falló", nombre, tenant_id)
        _latido_de_error(nombre, tenant_id, e)
        return None


def procesar_cola(tenant_id: str, nombre_cola: str, handler: Handler, contexto: dict[str, Any], max_jobs: int = MAX_JOBS_POR_COLA_POR_VUELTA) -> int:
    procesados = 0
    for _ in range(max_jobs):
        with tenant_session(tenant_id) as s:
            job = cola_mod.tomar(s, nombre_cola, lease_seg=LEASE_SEG)
        if job is None:
            break
        try:
            with tenant_session(tenant_id) as s:
                handler(s, job, contexto)
                # Fencing (A-06): la validación del lease y los efectos del handler se
                # confirman en la MISMA transacción. Si el lease ya no es nuestro, LeaseAjeno
                # hace rollback de todo lo que el handler escribió — nunca se confirman
                # efectos de un worker que perdió la propiedad.
                cola_mod.completar(s, job.id, job.lease_token)
        except cola_mod.LeaseAjeno:
            # Otro worker readquirió la tarea: este no completa, no falla, no reintenta.
            log.warning("job %s (%s): lease perdido, efectos revertidos", job.id, nombre_cola)
        except Exception:
            log.exception("job %s (%s) falló", job.id, nombre_cola)
            try:
                with tenant_session(tenant_id) as s:
                    cola_mod.fallar(s, job.id, job.lease_token)
            except cola_mod.LeaseAjeno:
                log.warning("job %s (%s): lease perdido al marcar el fallo", job.id, nombre_cola)
        procesados += 1
    return procesados


def correr_una_vuelta(storage: Storage, publicador: Publicador, handlers: dict[str, Handler] | None = None) -> dict[str, Any]:
    handlers = handlers or HANDLERS
    contexto = {"publicador": publicador, "storage": storage}
    ahora = ahora_utc()
    resumen: dict[str, Any] = {"tenants": 0, "outbox_publicados": 0, "jobs": 0}
    for tenant_id in listar_tenants():
        resumen["tenants"] += 1

        def _drenar() -> int:
            with tenant_session(tenant_id) as s:
                n = drenar_outbox(s, tenant_id, publicador)
                latir(s, "drenaje_outbox", tenant_id, True, {"publicados": n})
                return n

        resumen["outbox_publicados"] += _con_latido("drenaje_outbox", tenant_id, _drenar) or 0

        for nombre_cola, handler in handlers.items():
            n = _con_latido(f"cola_{nombre_cola}", tenant_id, lambda: procesar_cola(tenant_id, nombre_cola, handler, contexto))
            resumen["jobs"] += n or 0

        def _reloj(nombre: str, fn: Callable[[Session], Any]) -> None:
            def _correr() -> Any:
                with tenant_session(tenant_id) as s:
                    return fn(s)

            _con_latido(nombre, tenant_id, _correr)

        _reloj("control_vencimientos", lambda s: control_vencimientos(s, tenant_id, ahora))
        _reloj("vencer_excepciones_y_constancias", lambda s: vencer_excepciones_y_constancias(s, tenant_id, ahora))
        # La retención maneja sus propias transacciones (borrado físico fuera de la tx).
        _con_latido("control_retencion", tenant_id, lambda: control_retencion(tenant_id, storage, ahora))

    # Latido global del worker (tenant NULL): "el loop está vivo".
    try:
        with platform_session() as s:
            latir(s, "worker", None, True, resumen)
    except Exception:
        log.exception("no se pudo registrar el latido global del worker")
    return resumen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Worker de Módulo 1")
    parser.add_argument("--una-vuelta", action="store_true", help="corre una pasada y sale")
    args = parser.parse_args(argv)
    logging.basicConfig(level=os.environ.get("WORKER_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")

    from app.storage import obtener_storage

    storage = obtener_storage()
    publicador = PublicadorEnLog()
    poll = float(os.environ.get("WORKER_POLL_SEG", "5"))
    while True:
        try:
            resumen = correr_una_vuelta(storage, publicador)
            log.info("vuelta: %s", resumen)
        except Exception:
            log.exception("la vuelta del worker falló")
        if args.una_vuelta:
            return 0
        time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())
