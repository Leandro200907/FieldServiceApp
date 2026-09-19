"""Alta operativa de tenant y usuario (v1 no expone endpoints de gestión de usuarios).

    # tenant nuevo (imprime tenant_id)
    .venv/Scripts/python scripts/crear_usuario.py tenant --slug acme --nombre "ACME SRL"

    # usuario: la contraseña se lee de la variable USUARIO_PASSWORD (nunca de argv ni del
    # historial del shell); se valida por BYTES UTF-8 (máximo 72) y nunca se trunca
    USUARIO_PASSWORD=... .venv/Scripts/python scripts/crear_usuario.py usuario \\
        --tenant-slug acme --email ana@acme.test --nombre Ana --rol supervisor --rol responsable_legajos

Corre con DATABASE_URL (rol de aplicación) y respeta RLS: sólo escribe dentro del tenant
elegido. Ni la contraseña ni el hash se imprimen.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

from sqlalchemy import text

from app.auth.identidad import Rol
from app.auth.passwords import PasswordDemasiadoLarga, hashear_password
from app.db import platform_session, tenant_session


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
    hash_ = hashear_password(password)  # PasswordDemasiadoLarga si supera 72 bytes: no se trunca
    with platform_session() as s:
        tenant_id = s.execute(text("SELECT modulo1.resolver_tenant_por_slug(:slug)"), {"slug": tenant_slug}).scalar()
    if tenant_id is None:
        raise SystemExit(f"tenant inexistente: {tenant_slug}")
    usuario_id = str(uuid.uuid4())
    with tenant_session(str(tenant_id)) as s:
        s.execute(
            text("INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles, sujeto_id) "
                 "VALUES (:u, :t, :e, :n, :h, :r, :sj)"),
            {"u": usuario_id, "t": str(tenant_id), "e": email, "n": nombre, "h": hash_, "r": roles, "sj": sujeto_id},
        )
    return usuario_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alta de tenant / usuario de Módulo 1")
    sub = parser.add_subparsers(dest="que", required=True)
    pt = sub.add_parser("tenant")
    pt.add_argument("--slug", required=True)
    pt.add_argument("--nombre", required=True)
    pt.add_argument("--zona-horaria")
    pu = sub.add_parser("usuario")
    pu.add_argument("--tenant-slug", required=True)
    pu.add_argument("--email", required=True)
    pu.add_argument("--nombre", required=True)
    pu.add_argument("--rol", action="append", required=True, choices=[r.value for r in Rol])
    pu.add_argument("--sujeto-id", help="legajo de la persona (obligatorio para el rol tecnico)")
    args = parser.parse_args(argv)

    if args.que == "tenant":
        print(crear_tenant(args.slug, args.nombre, args.zona_horaria))
        return 0
    password = os.environ.get("USUARIO_PASSWORD")
    if not password:
        print("Falta USUARIO_PASSWORD en el entorno", file=sys.stderr)
        return 2
    try:
        print(crear_usuario(args.tenant_slug, args.email, args.nombre, args.rol, password, args.sujeto_id))
    except PasswordDemasiadoLarga as e:
        print(f"{e.codigo}: {e}", file=sys.stderr)  # sin la contraseña
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
