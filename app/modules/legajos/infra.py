"""Infraestructura mínima compartida por los routers de comandos de Evidencia y
Requisitos: ejecución uniforme de un comando (rol → tenant_session → Idempotency-Key →
efecto → guardar resultado).

`app.modules.requisitos.router` importa de acá para no duplicar; ambos paquetes son de
la misma pieza (Comandos Evidencia + Requisitos).
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Header
from sqlalchemy.orm import Session

from app.auth.identidad import Identidad, Rol
from app.comun.idempotencia import ejecutar_idempotente, fingerprint_de


def clave_idempotencia(idempotency_key: str | None = Header(None, alias="Idempotency-Key")) -> str | None:
    return idempotency_key


def ejecutar_comando(
    identidad: Identidad,
    clave: str | None,
    roles: tuple[Rol, ...],
    efecto: Callable[[Session], dict[str, Any]],
    *,
    ruta: str,
    body: Any,
) -> dict[str, Any]:
    """Patrón único de todo POST /comandos/*:

    1. Permiso por rol (matriz 2.2) — antes de abrir nada.
    2. Idempotencia con reserva atómica (A-03): `ejecutar_idempotente` reserva la clave en
       una transacción corta, corre el efecto en su propia `tenant_session` y consolida el
       resultado en esa misma transacción. Con la misma clave: replay exacto si el
       fingerprint (ruta + body) coincide, 409 si difiere o si otra solicitud está en curso.
    """
    identidad.exigir_rol(*roles)
    return ejecutar_idempotente(identidad.tenant_id, clave, fingerprint_de("POST", ruta, body), efecto)
