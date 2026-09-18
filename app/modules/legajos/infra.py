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
from app.comun.idempotencia import buscar_resultado, guardar_resultado
from app.db import tenant_session


def clave_idempotencia(idempotency_key: str | None = Header(None, alias="Idempotency-Key")) -> str | None:
    return idempotency_key


def ejecutar_comando(
    identidad: Identidad,
    clave: str | None,
    roles: tuple[Rol, ...],
    efecto: Callable[[Session], dict[str, Any]],
) -> dict[str, Any]:
    """Patrón único de todo POST /comandos/*:

    1. Permiso por rol (matriz 2.2) — antes de abrir nada.
    2. Una sola `tenant_session` por request.
    3. Si `Idempotency-Key` ya tiene resultado, se devuelve tal cual sin re-aplicar.
    4. Se ejecuta el efecto (servicio) y se guarda su resultado bajo la clave, en la
       misma transacción: clave y efecto son atómicos.
    """
    identidad.exigir_rol(*roles)
    with tenant_session(identidad.tenant_id) as s:
        previo = buscar_resultado(s, identidad.tenant_id, clave)
        if previo is not None:
            return previo
        resultado = efecto(s)
        guardar_resultado(s, identidad.tenant_id, clave, resultado)
        return resultado
