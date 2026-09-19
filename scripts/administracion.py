"""Administración inicial por CLI (v1 no expone endpoints ni pantallas de usuarios).

Procedimiento completo para un tenant nuevo (corre con DATABASE_URL del ENV_FILE, rol de
aplicación, respetando RLS: sólo escribe dentro del tenant elegido):

    # 1) tenant (imprime el tenant_id)
    python scripts/administracion.py crear-tenant --slug acme --nombre "ACME SRL" [--zona-horaria ...]

    # 2) primer responsable de legajos (y/o configuración)
    python scripts/administracion.py crear-usuario --tenant-slug acme --email ana@acme.test \\
        --nombre Ana --rol responsable_legajos --rol configuracion

    # 3) supervisor
    python scripts/administracion.py crear-usuario --tenant-slug acme --email sup@acme.test --nombre Sup --rol supervisor

    # 4) desactivar (bloquea login y refresh; revoca sus refresh tokens)
    python scripts/administracion.py desactivar-usuario --tenant-slug acme --email sup@acme.test

    # listar
    python scripts/administracion.py listar-usuarios --tenant-slug acme

Contraseña: NUNCA por argv ni stdout. Se toma de la variable `USUARIO_PASSWORD` si está
definida; si no, se pide dos veces por prompt seguro (`getpass`, sin eco) — y si no hay
terminal interactiva, falla con código 2. Límite: 72 bytes UTF-8 (bcrypt), sin truncar.

Desactivación: efectiva de inmediato en todas las instancias — cada request protegido
comprueba `activo` en la base (app/auth/dependencies.py); login y refresh responden 401 y
los refresh tokens quedan revocados. No hay reactivación en v1.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # ejecutable desde cualquier cwd

from app.auth.identidad import Rol  # noqa: E402
from app.auth.passwords import PasswordDemasiadoLarga, hashear_password, validar_longitud  # noqa: E402
from app.db import platform_session, tenant_session  # noqa: E402


class ErrorDeAdministracion(SystemExit):
    def __init__(self, mensaje: str):
        print(mensaje, file=sys.stderr)
        super().__init__(2)


def _tenant_id(slug: str) -> str:
    with platform_session() as s:
        tenant_id = s.execute(text("SELECT modulo1.resolver_tenant_por_slug(:slug)"), {"slug": slug}).scalar()
    if tenant_id is None:
        raise ErrorDeAdministracion(f"tenant inexistente: {slug}")
    return str(tenant_id)


def obtener_password() -> str:
    """USUARIO_PASSWORD si está; si no, prompt seguro por duplicado. Nunca argv."""
    password = os.environ.get("USUARIO_PASSWORD")
    if password:
        validar_longitud(password)
        return password
    if not sys.stdin.isatty():
        raise ErrorDeAdministracion("Falta USUARIO_PASSWORD y no hay terminal para pedir la contraseña")
    p1 = getpass.getpass("Contraseña: ")
    p2 = getpass.getpass("Repetir contraseña: ")
    if p1 != p2:
        raise ErrorDeAdministracion("Las contraseñas no coinciden")
    if not p1:
        raise ErrorDeAdministracion("La contraseña no puede estar vacía")
    validar_longitud(p1)
    return p1


def crear_tenant(slug: str, nombre: str, zona_horaria: str | None) -> str:
    tenant_id = str(uuid.uuid4())
    with tenant_session(tenant_id) as s:
        s.execute(
            text("INSERT INTO modulo1.tenant (tenant_id, nombre, slug, zona_horaria) "
                 "VALUES (:t, :n, :slug, COALESCE(:tz, 'America/Argentina/Buenos_Aires'))"),
            {"t": tenant_id, "n": nombre, "slug": slug, "tz": zona_horaria},
        )
    return tenant_id


def crear_usuario(tenant_slug: str, email: str, nombre: str, roles: list[str], password: str, sujeto_id: str | None) -> str:
    if "tecnico" in roles and not sujeto_id:
        raise ErrorDeAdministracion("El rol tecnico exige --sujeto-id (legajo de la persona)")
    hash_ = hashear_password(password)  # PasswordDemasiadoLarga si supera 72 bytes: no se trunca
    tenant_id = _tenant_id(tenant_slug)
    usuario_id = str(uuid.uuid4())
    with tenant_session(tenant_id) as s:
        s.execute(
            text("INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles, sujeto_id) "
                 "VALUES (:u, :t, :e, :n, :h, :r, :sj)"),
            {"u": usuario_id, "t": tenant_id, "e": email, "n": nombre, "h": hash_, "r": roles, "sj": sujeto_id},
        )
    return usuario_id


def desactivar_usuario(tenant_slug: str, email: str) -> dict[str, int | str]:
    """activo=false + revocación de todos sus refresh tokens vigentes. Idempotente."""
    tenant_id = _tenant_id(tenant_slug)
    with tenant_session(tenant_id) as s:
        usuario_id = s.execute(
            text("UPDATE modulo1.usuario SET activo = false WHERE tenant_id = :t AND lower(email) = lower(:e) RETURNING usuario_id"),
            {"t": tenant_id, "e": email},
        ).scalar()
        if usuario_id is None:
            raise ErrorDeAdministracion(f"usuario inexistente en {tenant_slug}: {email}")
        revocados = s.execute(
            text("UPDATE modulo1.refresh_token SET revocado_en = now() WHERE tenant_id = :t AND usuario_id = :u AND revocado_en IS NULL"),
            {"t": tenant_id, "u": str(usuario_id)},
        ).rowcount
    return {"usuario_id": str(usuario_id), "refresh_tokens_revocados": int(revocados)}


def listar_usuarios(tenant_slug: str) -> list[dict]:
    tenant_id = _tenant_id(tenant_slug)
    with tenant_session(tenant_id) as s:
        return [dict(f) for f in s.execute(
            text("SELECT usuario_id, email, nombre, roles, sujeto_id, activo FROM modulo1.usuario WHERE tenant_id = :t ORDER BY email"),
            {"t": tenant_id},
        ).mappings()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Administración inicial de Módulo 1 (tenants y usuarios)")
    sub = parser.add_subparsers(dest="que", required=True)
    pt = sub.add_parser("crear-tenant")
    pt.add_argument("--slug", required=True)
    pt.add_argument("--nombre", required=True)
    pt.add_argument("--zona-horaria")
    pu = sub.add_parser("crear-usuario")
    pu.add_argument("--tenant-slug", required=True)
    pu.add_argument("--email", required=True)
    pu.add_argument("--nombre", required=True)
    pu.add_argument("--rol", action="append", required=True, choices=[r.value for r in Rol])
    pu.add_argument("--sujeto-id", help="legajo de la persona (obligatorio para el rol tecnico)")
    pd = sub.add_parser("desactivar-usuario")
    pd.add_argument("--tenant-slug", required=True)
    pd.add_argument("--email", required=True)
    pl = sub.add_parser("listar-usuarios")
    pl.add_argument("--tenant-slug", required=True)
    args = parser.parse_args(argv)

    try:
        if args.que == "crear-tenant":
            print(crear_tenant(args.slug, args.nombre, args.zona_horaria))
        elif args.que == "crear-usuario":
            print(crear_usuario(args.tenant_slug, args.email, args.nombre, args.rol, obtener_password(), args.sujeto_id))
        elif args.que == "desactivar-usuario":
            r = desactivar_usuario(args.tenant_slug, args.email)
            print(f"desactivado {r['usuario_id']} (refresh tokens revocados: {r['refresh_tokens_revocados']})")
        elif args.que == "listar-usuarios":
            for u in listar_usuarios(args.tenant_slug):
                print(f"{u['usuario_id']}  {u['email']}  {','.join(u['roles'])}  {'activo' if u['activo'] else 'INACTIVO'}")
    except PasswordDemasiadoLarga as e:
        print(f"{e.codigo}: {e}", file=sys.stderr)  # sin la contraseña
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
