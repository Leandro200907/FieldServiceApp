"""Endpoints de autenticación (9.2). Montados por app/main.py bajo /v1 → /v1/auth/*.

Login es el único lugar donde todavía no hay tenant en sesión: se resuelve el tenant por
slug con la función SECURITY DEFINER `modulo1.resolver_tenant_por_slug` (platform_session,
sin RLS del tenant) y recién con ese id se abre `tenant_session`. Toda respuesta de
credenciales malas es el mismo 401 genérico: no se revela si el slug o el email existen.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import NoAutenticado
from app.auth import jwt as tokens
from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.auth.passwords import hashear_password, verificar_password
from app.db import platform_session, tenant_session

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash "de relleno" para que un email inexistente cueste lo mismo que una password mala
# (evita el oráculo por tiempo de respuesta). Se calcula una vez al importar.
_HASH_SENUELO = hashear_password("senuelo-no-es-una-password-valida")


# --------------------------------------------------------------------------- schemas


class LoginRequest(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class ParDeTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class IdentidadResponse(BaseModel):
    tenant_id: str
    usuario_id: str
    roles: list[str]
    sujeto_id: str | None


# --------------------------------------------------------------------------- endpoints


@router.post("/login", response_model=ParDeTokens)
def login(body: LoginRequest) -> ParDeTokens:
    with platform_session() as s:
        tenant_id = s.execute(
            text("SELECT modulo1.resolver_tenant_por_slug(:slug)"), {"slug": body.tenant_slug}
        ).scalar()
    if tenant_id is None:
        # Mismo costo que una password mala, misma respuesta.
        verificar_password(body.password, _HASH_SENUELO)
        raise NoAutenticado("Credenciales inválidas")

    with tenant_session(str(tenant_id)) as s:
        usuario = _buscar_usuario_por_email(s, body.email)
        hash_guardado = usuario["password_hash"] if usuario else _HASH_SENUELO
        if not verificar_password(body.password, hash_guardado) or usuario is None or not usuario["activo"]:
            raise NoAutenticado("Credenciales inválidas")
        return _emitir_par(s, str(tenant_id), usuario)


@router.post("/refresh", response_model=ParDeTokens)
def refresh(body: RefreshRequest) -> ParDeTokens:
    claims = tokens.validar_refresh_token(body.refresh_token)
    with tenant_session(str(claims["tenant_id"])) as s:
        # Rotación: el viejo queda revocado en esta misma transacción o no se emite nada.
        usuario_id = tokens.consumir_refresh_token(s, body.refresh_token)
        if usuario_id != str(claims["sub"]):
            raise NoAutenticado("Refresh token inválido")
        usuario = _buscar_usuario_por_id(s, usuario_id)
        if usuario is None or not usuario["activo"]:
            raise NoAutenticado("Usuario inactivo")
        return _emitir_par(s, str(claims["tenant_id"]), usuario)


@router.post("/logout")
def logout(body: LogoutRequest, identidad: Identidad = Depends(identidad_actual)) -> dict:
    """Revoca el refresh token. Idempotente: si ya estaba revocado o no es del tenant
    (RLS), simplemente informa `revocado: false`. No se decodifica el token del body —
    con el hash alcanza, y así un refresh malformado tampoco filtra información."""
    with tenant_session(identidad.tenant_id) as s:
        revocado = tokens.revocar_refresh_token(s, body.refresh_token)
    return {"revocado": revocado}


@router.get("/yo", response_model=IdentidadResponse)
def yo(identidad: Identidad = Depends(identidad_actual)) -> IdentidadResponse:
    return IdentidadResponse(
        tenant_id=identidad.tenant_id,
        usuario_id=identidad.usuario_id,
        roles=sorted(r.value for r in identidad.roles),
        sujeto_id=identidad.sujeto_id,
    )


# --------------------------------------------------------------------------- helpers


_COLUMNAS_USUARIO = "usuario_id, password_hash, roles, sujeto_id, activo"


def _buscar_usuario_por_email(s: Session, email: str) -> dict | None:
    fila = s.execute(
        text(f"SELECT {_COLUMNAS_USUARIO} FROM modulo1.usuario WHERE lower(email) = lower(:e)"),
        {"e": email.strip()},
    ).mappings().first()
    return dict(fila) if fila else None


def _buscar_usuario_por_id(s: Session, usuario_id: str) -> dict | None:
    fila = s.execute(
        text(f"SELECT {_COLUMNAS_USUARIO} FROM modulo1.usuario WHERE usuario_id = :u"),
        {"u": usuario_id},
    ).mappings().first()
    return dict(fila) if fila else None


def _emitir_par(s: Session, tenant_id: str, usuario: dict) -> ParDeTokens:
    identidad = Identidad(
        tenant_id=tenant_id,
        usuario_id=str(usuario["usuario_id"]),
        roles=frozenset(Rol(r) for r in usuario["roles"]),
        sujeto_id=usuario["sujeto_id"],
    )
    access, expira_en = tokens.emitir_access_token(identidad)
    refresh_token = tokens.emitir_refresh_token(s, tenant_id, identidad.usuario_id)
    return ParDeTokens(access_token=access, refresh_token=refresh_token, expires_in=expira_en)
