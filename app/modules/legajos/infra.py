"""Infraestructura mínima compartida por los routers de comandos de Evidencia y
Requisitos: resolución de la identidad autenticada y ejecución uniforme de un comando
(rol → tenant_session → Idempotency-Key → efecto → guardar resultado).

`app.modules.requisitos.router` importa de acá para no duplicar; ambos paquetes son de
la misma pieza (Comandos Evidencia + Requisitos).
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Header
from sqlalchemy.orm import Session

from app.api.errores import NoAutenticado
from app.auth.identidad import Identidad, Rol
from app.comun.idempotencia import buscar_resultado, guardar_resultado
from app.db import tenant_session

try:  # Contrato del brief: la construye la pieza Auth.
    from app.auth.dependencies import identidad_actual  # noqa: F401
except ImportError:  # pragma: no cover - solo mientras Auth no exista
    # FALLBACK LOCAL — SE BORRA EN INTEGRACIÓN. Decodifica el JWT con los claims del brief
    # ({sub, tenant_id, roles, sujeto_id, exp}) firmado con settings.jwt_secret.
    import jwt as _jwt

    from app.config import settings as _settings

    def identidad_actual(authorization: str | None = Header(None)) -> Identidad:  # type: ignore[misc]
        if not authorization or not authorization.lower().startswith("bearer "):
            raise NoAutenticado("Falta el token de acceso")
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = _jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
        except _jwt.PyJWTError as e:
            raise NoAutenticado("Token inválido o vencido", {"motivo": str(e)}) from e
        tenant_id = claims.get("tenant_id")
        usuario_id = claims.get("sub")
        if not tenant_id or not usuario_id:
            raise NoAutenticado("Token sin tenant o sin usuario")
        roles = frozenset(Rol(r) for r in claims.get("roles", []) if r in {x.value for x in Rol})
        return Identidad(
            tenant_id=str(tenant_id),
            usuario_id=str(usuario_id),
            roles=roles,
            sujeto_id=claims.get("sujeto_id"),
        )


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
