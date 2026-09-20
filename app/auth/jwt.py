"""Emisión y validación de JWT propios (9.2).

Dos tipos de token, ambos firmados con `settings.jwt_secret` / `jwt_algorithm`:

- access: claims EXACTOS del contrato del brief —
  `sub` (usuario_id), `tenant_id`, `roles`, `sujeto_id`, `iat`, `exp`, `tipo="access"`.
  Es stateless: alcanza con la firma y la expiración, no se consulta la base por request.
- refresh: `sub`, `tenant_id`, `jti`, `iat`, `exp`, `tipo="refresh"`. Se persiste en
  `modulo1.refresh_token` SOLO su hash SHA-256 (nunca el token), es revocable y se rota
  en cada uso: el viejo queda revocado en la misma transacción que emite el nuevo.

El tenant_id de un token es la única fuente del tenant en runtime (regla dura 1): el
dependency de auth arma `Identidad` a partir de estos claims y nada más.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta

import jwt as pyjwt
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import NoAutenticado
from app.auth.identidad import Identidad, Rol
from app.comun.reloj import ahora_utc
from app.config import settings

TIPO_ACCESS = "access"
TIPO_REFRESH = "refresh"


# --------------------------------------------------------------------------- access


def emitir_access_token(identidad: Identidad, ahora: datetime | None = None) -> tuple[str, int]:
    """Devuelve (token, segundos hasta que expire)."""
    instante = ahora or ahora_utc()
    duracion = timedelta(minutes=settings.jwt_access_token_minutes)
    claims = {
        "sub": str(identidad.usuario_id),
        "tenant_id": str(identidad.tenant_id),
        "roles": sorted(r.value for r in identidad.roles),
        "sujeto_id": identidad.sujeto_id,
        "iat": instante,
        "exp": instante + duracion,
        "tipo": TIPO_ACCESS,
    }
    return _firmar(claims), int(duracion.total_seconds())


def validar_access_token(token: str) -> Identidad:
    """Decodifica y valida un access token; cualquier problema (firma, vencimiento,
    tipo distinto de access, claims faltantes o roles desconocidos) es `NoAutenticado`.
    No toca la base: el estado actual del usuario lo comprueba `identidad_actual` en cada request."""
    claims = decodificar(token, tipo_esperado=TIPO_ACCESS)
    try:
        roles = frozenset(Rol(r) for r in claims.get("roles") or [])
    except ValueError:
        raise NoAutenticado("Token con roles desconocidos")
    sujeto_id = claims.get("sujeto_id")
    return Identidad(
        tenant_id=str(claims["tenant_id"]),
        usuario_id=str(claims["sub"]),
        roles=roles,
        sujeto_id=str(sujeto_id) if sujeto_id is not None else None,
    )


# --------------------------------------------------------------------------- refresh


def emitir_refresh_token(session: Session, tenant_id: str, usuario_id: str, ahora: datetime | None = None) -> str:
    """Emite un refresh token y persiste su hash. `session` tiene que ser una
    `tenant_session(tenant_id)` abierta — RLS exige que el tenant coincida."""
    instante = ahora or ahora_utc()
    expira = instante + timedelta(days=settings.jwt_refresh_token_days)
    claims = {
        "sub": str(usuario_id),
        "tenant_id": str(tenant_id),
        "jti": uuid.uuid4().hex,
        "iat": instante,
        "exp": expira,
        "tipo": TIPO_REFRESH,
    }
    token = _firmar(claims)
    session.execute(
        text(
            "INSERT INTO modulo1.refresh_token (token_hash, tenant_id, usuario_id, expira_en) "
            "VALUES (:h, :t, :u, :exp)"
        ),
        {"h": hash_de_token(token), "t": str(tenant_id), "u": str(usuario_id), "exp": expira},
    )
    return token


def validar_refresh_token(token: str) -> dict:
    """Solo verifica firma/vencimiento/tipo y devuelve los claims. La revocación se
    chequea contra la tabla, dentro de `tenant_session(claims["tenant_id"])`."""
    claims = decodificar(token, tipo_esperado=TIPO_REFRESH)
    if not claims.get("jti"):
        raise NoAutenticado("Refresh token inválido")
    return claims


def consumir_refresh_token(session: Session, token: str, ahora: datetime | None = None) -> str:
    """Marca el refresh token como revocado y devuelve el usuario_id dueño. Es un solo
    UPDATE condicional: si ya estaba revocado, vencido o no existe (o pertenece a otro
    tenant — RLS), no devuelve fila y se rechaza. Así dos refresh concurrentes con el
    mismo token no pueden emitir dos pares nuevos."""
    instante = ahora or ahora_utc()
    fila = session.execute(
        text(
            "UPDATE modulo1.refresh_token SET revocado_en = :ahora "
            "WHERE token_hash = :h AND revocado_en IS NULL AND expira_en > :ahora "
            "RETURNING usuario_id"
        ),
        {"h": hash_de_token(token), "ahora": instante},
    ).first()
    if fila is None:
        raise NoAutenticado("Refresh token revocado o vencido")
    return str(fila[0])


def revocar_refresh_token(session: Session, token: str, ahora: datetime | None = None) -> bool:
    """Revoca sin rotar (logout). Idempotente: devuelve False si ya no estaba vigente."""
    instante = ahora or ahora_utc()
    fila = session.execute(
        text(
            "UPDATE modulo1.refresh_token SET revocado_en = :ahora "
            "WHERE token_hash = :h AND revocado_en IS NULL RETURNING token_hash"
        ),
        {"h": hash_de_token(token), "ahora": instante},
    ).first()
    return fila is not None


def hash_de_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- común


def decodificar(token: str, tipo_esperado: str) -> dict:
    try:
        claims = pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "tenant_id", "exp", "iat"]},
        )
    except pyjwt.ExpiredSignatureError:
        raise NoAutenticado("Token vencido")
    except pyjwt.PyJWTError:
        raise NoAutenticado("Token inválido")
    if claims.get("tipo") != tipo_esperado:
        raise NoAutenticado("Tipo de token incorrecto")
    return claims


def _firmar(claims: dict) -> str:
    return pyjwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
