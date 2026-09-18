"""Dependency de FastAPI que convierte el header Authorization en una `Identidad`.

    from app.auth.dependencies import identidad_actual
    def endpoint(identidad: Identidad = Depends(identidad_actual)): ...

Es stateless a propósito: valida firma, vencimiento y tipo del access token y arma la
Identidad con los claims. No consulta la base por request — un usuario desactivado deja
de poder entrar cuando vence su access token (minutos) y su refresh ya no rota. El
tenant_id sale SOLO del claim (regla dura 1); ninguna capa lo acepta por otra vía.
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errores import NoAutenticado
from app.auth.identidad import Identidad
from app.auth.jwt import validar_access_token

# auto_error=False: si falta el header queremos nuestro envelope 401 (`NoAutenticado`),
# no el HTTPException 403 que HTTPBearer arma por defecto.
_bearer = HTTPBearer(auto_error=False)


def identidad_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Identidad:
    if credenciales is None or credenciales.scheme.lower() != "bearer" or not credenciales.credentials:
        raise NoAutenticado("Falta el token de acceso")
    return validar_access_token(credenciales.credentials)
