"""Precarga / actualización del catálogo global de industria (plataforma.*) desde un JSON.

    ENV_FILE=.env .venv/Scripts/python scripts/precargar_plantillas.py docs/plantillas/base_v1.json

Corre con DATABASE_URL_MIGRATIONS (rol owner): el catálogo global es "mecanismo de
plataforma", el rol de aplicación sólo lo lee (no-funcionales 1.5.2). Idempotente y
opt-in hacia los tenants: sólo escribe en `plataforma`; nunca toca copias locales.
- Definición nueva → INSERT; existente con `version` mayor en el JSON → UPDATE (sube la
  versión y `actualizado_en`); versión igual o menor → sin cambios.
- Matriz: ídem por (operadora, tipo_servicio); al subir la versión se reemplazan sus líneas.
El reloj del worker (`control_plantillas`) detecta las copias locales atrasadas y avisa.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.entorno import archivo_de_entorno  # noqa: E402


def _dsn_owner() -> str:
    import os
    ruta = Path(archivo_de_entorno())
    valores = {}
    if ruta.is_file():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                valores[k.strip()] = v.strip()
    dsn = os.environ.get("DATABASE_URL_MIGRATIONS") or valores.get("DATABASE_URL_MIGRATIONS")
    if not dsn:
        raise SystemExit("Falta DATABASE_URL_MIGRATIONS (rol owner)")
    return dsn.replace("postgresql+psycopg://", "postgresql://")


def precargar(conn, datos: dict) -> dict[str, int]:
    """Aplica el JSON sobre una conexión psycopg abierta (autocommit off). Devuelve conteos."""
    r = {"definiciones_nuevas": 0, "definiciones_actualizadas": 0, "matrices_nuevas": 0, "matrices_actualizadas": 0}
    ids: dict[str, str] = {}
    for d in datos["definiciones"]:
        fila = conn.execute(
            "SELECT definicion_global_id, version FROM plataforma.definicion_requisito_global "
            "WHERE nombre = %s AND categoria = %s AND tipo_sujeto_aplicable = %s",
            (d["nombre"], d["categoria"], d["tipo_sujeto_aplicable"]),
        ).fetchone()
        if fila is None:
            gid = conn.execute(
                "INSERT INTO plataforma.definicion_requisito_global (nombre, categoria, tipo_sujeto_aplicable, version, descripcion) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING definicion_global_id",
                (d["nombre"], d["categoria"], d["tipo_sujeto_aplicable"], d.get("version", 1), d.get("descripcion")),
            ).fetchone()[0]
            r["definiciones_nuevas"] += 1
        else:
            gid = fila[0]
            if d.get("version", 1) > fila[1]:
                conn.execute(
                    "UPDATE plataforma.definicion_requisito_global SET version = %s, descripcion = %s, actualizado_en = now() "
                    "WHERE definicion_global_id = %s",
                    (d["version"], d.get("descripcion"), gid),
                )
                r["definiciones_actualizadas"] += 1
        ids[d["nombre"]] = str(gid)

    lineas_ref: list | None = None
    for m in datos["matrices"]:
        lineas = m["lineas"]
        if lineas == "como YPF":
            lineas = lineas_ref
        elif isinstance(lineas, list) and lineas_ref is None:
            lineas_ref = lineas
        assert isinstance(lineas, list), "líneas de matriz no resueltas"
        fila = conn.execute(
            "SELECT matriz_global_id, version FROM plataforma.matriz_global WHERE operadora = %s AND tipo_servicio = %s",
            (m["operadora"], m["tipo_servicio"]),
        ).fetchone()
        if fila is None:
            mid = conn.execute(
                "INSERT INTO plataforma.matriz_global (operadora, tipo_servicio, descripcion, version, fuente) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING matriz_global_id",
                (m["operadora"], m["tipo_servicio"], m.get("descripcion"), m.get("version", 1), m.get("fuente")),
            ).fetchone()[0]
            r["matrices_nuevas"] += 1
        else:
            mid = fila[0]
            if m.get("version", 1) <= fila[1]:
                continue
            conn.execute(
                "UPDATE plataforma.matriz_global SET version = %s, descripcion = %s, fuente = %s, actualizado_en = now() WHERE matriz_global_id = %s",
                (m["version"], m.get("descripcion"), m.get("fuente"), mid),
            )
            conn.execute("DELETE FROM plataforma.linea_matriz_global WHERE matriz_global_id = %s", (mid,))
            r["matrices_actualizadas"] += 1
        for ln in lineas:
            conn.execute(
                "INSERT INTO plataforma.linea_matriz_global (matriz_global_id, definicion_global_id, clasificacion, bloqueante_durante_ejecucion) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (mid, ids[ln["definicion"]], ln["clasificacion"], ln.get("bloqueante_durante_ejecucion", False)),
            )
    return r


def main(argv: list[str] | None = None) -> int:
    import psycopg

    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: precargar_plantillas.py <archivo.json>", file=sys.stderr)
        return 2
    datos = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    with psycopg.connect(_dsn_owner()) as conn:
        resultado = precargar(conn, datos)
        conn.commit()
    print(resultado)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
