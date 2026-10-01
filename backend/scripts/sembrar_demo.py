"""Sembrado de base de demo Módulo 1.

Uso (desde backend/, con ENV_FILE apuntando a .env de fsm_demo):

    python scripts/sembrar_demo.py [--reset] [--importar-planillas]

La contraseña de usuarios demo: variable DEMO_PASSWORD o prompt getpass (nunca argv).
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.auth.passwords import validar_longitud  # noqa: E402
from app.storage import obtener_storage  # noqa: E402
from scripts.demo.config import NOMBRES_PERSONA, TENANTS, TenantDemo  # noqa: E402
from scripts.demo.contexto import EstadoTenant, crear_usuarios_demo  # noqa: E402
from scripts.demo.db_util import (  # noqa: E402
    ErrorDemo,
    borrar_storage_tenants,
    exigir_base_demo,
    precargar_plantillas_json,
    reset_base,
    tenant_ids_por_slugs,
)
from scripts.demo.planillas import generar_planillas, importar_planillas  # noqa: E402
from scripts.demo.reporte import imprimir_paquetes, imprimir_resumen, imprimir_tabla_usuarios  # noqa: E402
from scripts.demo.semilla_tenant import SemillaContext, sembrar_tenant  # noqa: E402


def obtener_demo_password() -> str:
    pwd = os.environ.get("DEMO_PASSWORD")
    if pwd:
        validar_longitud(pwd)
        return pwd
    if not sys.stdin.isatty():
        raise ErrorDemo("Falta DEMO_PASSWORD y no hay terminal para getpass")
    p1 = getpass.getpass("Contraseña demo: ")
    p2 = getpass.getpass("Repetir contraseña demo: ")
    if p1 != p2 or not p1:
        raise ErrorDemo("Las contraseñas demo no coinciden o están vacías")
    validar_longitud(p1)
    return p1


def correr_worker_una_vuelta() -> None:
    from app.worker import main as worker_main

    worker_main.main(["--una-vuelta"])


def reconocer_una_alerta(est: EstadoTenant) -> None:
    from sqlalchemy import text

    from app.db import tenant_session
    from app.modules.alertas import servicio as alertas_svc

    with tenant_session(est.tenant_id) as s:
        fila = s.execute(
            text(
                "SELECT alerta_id::text FROM modulo1.alerta_vencimiento "
                "WHERE tenant_id = :t ORDER BY creado_en LIMIT 1"
            ),
            {"t": est.tenant_id},
        ).scalar()
        if not fila:
            return
        idn = est.idn("supervisor", 1)
        alertas_svc.reconocer(s, idn, alerta_id=fila, comentario="Visto en demo")
        est.alerta_id = fila


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sembrado de datos demo (_demo)")
    parser.add_argument("--reset", action="store_true", help="Recrea la base _demo y storage de tenants demo")
    parser.add_argument("--importar-planillas", action="store_true", help="Importa presentaciones_1/2 y oc.xlsx")
    args = parser.parse_args(argv)

    dsn_app, dsn_owner, nombre_base = exigir_base_demo()
    slugs = [t.slug for t in TENANTS]

    if args.reset:
        ids_viejos = list(tenant_ids_por_slugs(dsn_app, slugs).values())
        n = borrar_storage_tenants(ids_viejos)
        print(f"Storage: {n} objetos borrados (tenants demo previos)")
        reset_base(dsn_owner, nombre_base)

    plantilla = RAIZ / "docs" / "plantillas" / "base_v1.json"
    precargar_plantillas_json(plantilla)

    password = obtener_demo_password()
    ctx = SemillaContext()
    estados: list[EstadoTenant] = []
    nombres = iter(NOMBRES_PERSONA)
    storage = obtener_storage()

    for spec in TENANTS:
        est = EstadoTenant(spec=spec, tenant_id="")
        crear_usuarios_demo(est, password, nombres)
        sembrar_tenant(est, storage, ctx)
        generar_planillas(est)
        if args.importar_planillas:
            try:
                importar_planillas(est, est.idn("responsable_legajos", 1))
            except Exception as e:  # noqa: BLE001
                ctx.fallas.append(f"importar_planillas {spec.slug}: {e}")
        estados.append(est)

    try:
        correr_worker_una_vuelta()
    except Exception as e:  # noqa: BLE001
        ctx.fallas.append(f"worker --una-vuelta: {e}")

    for est in estados:
        try:
            reconocer_una_alerta(est)
        except Exception as e:  # noqa: BLE001
            ctx.fallas.append(f"reconocer_alerta {est.spec.slug}: {e}")

    imprimir_tabla_usuarios(estados)
    imprimir_paquetes(estados)
    imprimir_resumen(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
