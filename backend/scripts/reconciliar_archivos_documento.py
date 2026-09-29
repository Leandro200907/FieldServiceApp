"""Reconcilia documento.archivo_estado con el storage real (auditoría B-3).

Uso: python -m scripts.reconciliar_archivos_documento [--tenant UUID] [--aplicar]
Sin --aplicar solo reporta filas confirmadas cuyo objeto no existe.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from app.db import platform_session, tenant_session
from app.storage import obtener_storage


def _tenants(tenant_id: str | None) -> list[str]:
    if tenant_id:
        return [tenant_id]
    with platform_session() as s:
        return [str(r[0]) for r in s.execute(text("SELECT * FROM modulo1.listar_tenants()")).all()]


def reconciliar(tenant_id: str, aplicar: bool) -> dict[str, int]:
    storage = obtener_storage()
    faltantes: list[str] = []
    with tenant_session(tenant_id) as s:
        filas = s.execute(text(
            "SELECT documento_id::text, clave_storage FROM modulo1.documento "
            "WHERE archivo_estado = 'confirmado' AND clave_storage IS NOT NULL"
        )).all()
        for doc_id, clave in filas:
            if not storage.existe(str(clave)):
                faltantes.append(doc_id)
        if aplicar and faltantes:
            s.execute(
                text(
                    "UPDATE modulo1.documento SET archivo_estado = 'sin_archivo', "
                    "archivo_validacion = 'invalido', archivo_validacion_motivo = 'archivo_ausente_en_storage' "
                    "WHERE documento_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": faltantes},
            )
    return {"revisados": len(filas), "faltantes": len(faltantes), "corregidos": len(faltantes) if aplicar else 0}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Reconciliar archivos confirmados con storage")
    p.add_argument("--tenant", help="UUID de tenant (todos si se omite)")
    p.add_argument("--aplicar", action="store_true", help="Marcar documentos sin archivo como sin_archivo/invalido")
    args = p.parse_args(argv)
    total = {"revisados": 0, "faltantes": 0, "corregidos": 0}
    for tid in _tenants(args.tenant):
        r = reconciliar(tid, args.aplicar)
        for k in total:
            total[k] += r[k]
        if r["faltantes"]:
            print(f"tenant {tid}: {r['faltantes']} confirmados sin objeto en storage")
    print(total)
    return 1 if total["faltantes"] and not args.aplicar else 0


if __name__ == "__main__":
    sys.exit(main())
