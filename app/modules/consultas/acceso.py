"""Acceso compartido por las piezas Consultas y OC: identidad autenticada y "universo"
del supervisor (2.2 de no-funcionales).

`identidad_actual` se toma de `app.auth.dependencies` (pieza Auth). Mientras esa pieza
no esté integrada, hay un fallback local mínimo que decodifica el JWT con los claims del
brief y arma `Identidad`. TODO integración: borrar el fallback y dejar solo el import.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.identidad import Identidad, Rol

try:  # pragma: no cover - la rama que corre depende de si Auth ya está integrada
    from app.auth.dependencies import identidad_actual  # noqa: F401
except ImportError:  # pragma: no cover
    import jwt as _pyjwt
    from fastapi import Depends as _Depends
    from fastapi.security import HTTPAuthorizationCredentials as _Cred
    from fastapi.security import HTTPBearer as _Bearer

    from app.api.errores import NoAutenticado as _NoAutenticado
    from app.config import settings as _settings

    _bearer = _Bearer(auto_error=False)

    def identidad_actual(credenciales: _Cred | None = _Depends(_bearer)) -> Identidad:  # type: ignore[misc]
        """Fallback provisorio — se borra cuando `app.auth.dependencies` exista."""
        if credenciales is None or not credenciales.credentials:
            raise _NoAutenticado("Falta el token de acceso")
        try:
            claims = _pyjwt.decode(
                credenciales.credentials,
                _settings.jwt_secret,
                algorithms=[_settings.jwt_algorithm],
                options={"require": ["sub", "tenant_id", "exp"]},
            )
            roles = frozenset(Rol(r) for r in claims.get("roles") or [])
        except (_pyjwt.PyJWTError, ValueError):
            raise _NoAutenticado("Token inválido")
        sujeto = claims.get("sujeto_id")
        return Identidad(
            tenant_id=str(claims["tenant_id"]),
            usuario_id=str(claims["sub"]),
            roles=roles,
            sujeto_id=str(sujeto) if sujeto is not None else None,
        )


def ve_todo_el_tenant(identidad: Identidad) -> bool:
    """responsable_legajos y configuracion ven toda la empresa; el resto se acota."""
    return identidad.tiene_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)


def universo_del_supervisor(session: Session, identidad: Identidad, hoy) -> list[str]:
    """Sujetos con `asignacion_supervisor` vigente hacia este usuario, más los
    vehículos/equipos bajo custodia vigente de esos sujetos (brief, "su universo")."""
    filas = session.execute(
        text(
            """
            WITH personas AS (
                SELECT sujeto_id FROM modulo1.asignacion_supervisor
                WHERE supervisor_usuario_id = :u AND estado = 'vigente' AND desde <= :hoy
            )
            SELECT sujeto_id FROM personas
            UNION
            SELECT c.recurso_id
            FROM modulo1.periodo_custodia p
            JOIN modulo1.custodia_recurso c ON c.custodia_id = p.custodia_id
            WHERE p.estado = 'vigente' AND p.custodio_id IN (SELECT sujeto_id FROM personas)
            """
        ),
        {"u": identidad.usuario_id, "hoy": hoy},
    ).all()
    return [f[0] for f in filas]


def alcance_de_sujetos(session: Session, identidad: Identidad, hoy) -> list[str] | None:
    """None = sin filtro (ve todo el tenant); lista = solo esos sujeto_id.

    Un técnico solo se ve a sí mismo; un supervisor, su universo. Un supervisor sin
    asignaciones ve una lista vacía, no todo (el filtro vacío no debe abrir el alcance).
    """
    if ve_todo_el_tenant(identidad):
        return None
    if identidad.tiene_rol(Rol.SUPERVISOR):
        return universo_del_supervisor(session, identidad, hoy)
    return [identidad.sujeto_id] if identidad.sujeto_id else []
