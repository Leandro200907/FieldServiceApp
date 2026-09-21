"""Dependency de FastAPI que convierte el header Authorization en una `Identidad`.

    from app.auth.dependencies import identidad_actual
    def endpoint(identidad: Identidad = Depends(identidad_actual)): ...

Valida firma, vencimiento y tipo del access token, arma la Identidad con los claims y
**comprueba en la base, en cada request protegido, que el usuario siga existiendo y
`activo=true`**. Así una desactivación (scripts/administracion.py) es efectiva de inmediato
en todas las instancias de la API, sin cachés ni memoria local: el access token vigente
deja de servir en el request siguiente. Usuario inexistente o inactivo → el mismo 401
genérico que un token inválido (no se revela cuál de los dos es).

El tenant_id sale SOLO del claim (regla dura 1); ninguna capa lo acepta por otra vía. La
consulta de estado corre en una `tenant_session` de ese tenant (RLS): un token de otro
tenant nunca "ve" al usuario.

Si en el futuro se incorpora la REACTIVACIÓN de usuarios, esta comprobación no alcanza:
un access/refresh token emitido antes de la desactivación volvería a ser válido. Habrá
que agregar `usuario.tokens_validos_desde` (o una versión de seguridad en el claim) y
rechazar todo token emitido antes de ese instante.

Sólo `/v1/salud/*` queda fuera de esta dependencia (rutas públicas).
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from app.api.errores import NoAutenticado
from app.auth.identidad import Identidad
from app.auth.jwt import validar_access_token
from app.db import tenant_session

# auto_error=False: si falta el header queremos nuestro envelope 401 (`NoAutenticado`),
# no el HTTPException 403 que HTTPBearer arma por defecto.
_bearer = HTTPBearer(auto_error=False)

_MENSAJE_GENERICO = "No autenticado"


def usuario_sigue_activo(tenant_id: str, usuario_id: str) -> bool:
    """Estado ACTUAL del usuario en la base (sin caché). False si no existe o está inactivo."""
    with tenant_session(tenant_id) as s:
        activo = s.execute(
            text("SELECT activo FROM modulo1.usuario WHERE tenant_id = :t AND usuario_id = :u"),
            {"t": tenant_id, "u": usuario_id},
        ).scalar()
    return bool(activo)


def identidad_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Identidad:
    if credenciales is None or credenciales.scheme.lower() != "bearer" or not credenciales.credentials:
        raise NoAutenticado("Falta el token de acceso")
    identidad = validar_access_token(credenciales.credentials)
    if not usuario_sigue_activo(identidad.tenant_id, identidad.usuario_id):
        raise NoAutenticado(_MENSAJE_GENERICO)
    return identidad
