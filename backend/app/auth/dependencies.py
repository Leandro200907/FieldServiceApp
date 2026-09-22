"""Dependency de FastAPI que convierte el header Authorization en una `Identidad`.

    from app.auth.dependencies import identidad_actual
    def endpoint(identidad: Identidad = Depends(identidad_actual)): ...

Valida firma, vencimiento y tipo del access token (para tenant_id/usuario_id — regla dura
1) y **reconstruye `roles`/`sujeto_id`/`activo` desde la fila actual de `usuario` en cada
request protegido**, nunca confiando en esos campos tal como vinieron en el JWT. Así tanto
una desactivación como un cambio de rol o de legajo (scripts/administracion.py, o una
corrección operativa directa) son efectivos de inmediato en todas las instancias de la
API, sin cachés ni memoria local: el access token vigente deja de servir el permiso viejo
en el request siguiente. Usuario inexistente o inactivo → el mismo 401 genérico que un
token inválido (no se revela cuál de los dos es).

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
from app.auth.identidad import Identidad, Rol
from app.auth.jwt import validar_access_token
from app.db import tenant_session

# auto_error=False: si falta el header queremos nuestro envelope 401 (`NoAutenticado`),
# no el HTTPException 403 que HTTPBearer arma por defecto.
_bearer = HTTPBearer(auto_error=False)

_MENSAJE_GENERICO = "No autenticado"


def _estado_actual_del_usuario(tenant_id: str, usuario_id: str) -> tuple[bool, list[str], str | None] | None:
    """Estado ACTUAL del usuario en la base (sin caché): (activo, roles, sujeto_id), o
    None si el usuario ya no existe."""
    with tenant_session(tenant_id) as s:
        fila = s.execute(
            text(
                "SELECT activo, roles, sujeto_id FROM modulo1.usuario "
                "WHERE tenant_id = :t AND usuario_id = :u"
            ),
            {"t": tenant_id, "u": usuario_id},
        ).first()
    if fila is None:
        return None
    activo, roles, sujeto_id = fila
    return bool(activo), list(roles or []), sujeto_id


def identidad_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Identidad:
    if credenciales is None or credenciales.scheme.lower() != "bearer" or not credenciales.credentials:
        raise NoAutenticado("Falta el token de acceso")
    identidad = validar_access_token(credenciales.credentials)
    estado = _estado_actual_del_usuario(identidad.tenant_id, identidad.usuario_id)
    if estado is None:
        raise NoAutenticado(_MENSAJE_GENERICO)
    activo, roles_db, sujeto_id_db = estado
    if not activo:
        raise NoAutenticado(_MENSAJE_GENERICO)
    try:
        roles = frozenset(Rol(r) for r in roles_db)
    except ValueError:
        raise NoAutenticado(_MENSAJE_GENERICO)
    return Identidad(
        tenant_id=identidad.tenant_id,
        usuario_id=identidad.usuario_id,
        roles=roles,
        sujeto_id=sujeto_id_db,
    )
