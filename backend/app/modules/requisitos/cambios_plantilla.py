"""Diferencias entre líneas de plantilla global y copia local de matriz."""
from __future__ import annotations

from typing import Any


def _idx_por_global(lineas: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for ln in lineas:
        gid = ln.get("definicion_global_id")
        if gid:
            out[str(gid)] = ln
    return out


def calcular_cambios_matriz(
    lineas_plantilla: list[dict[str, Any]],
    lineas_local: list[dict[str, Any]],
    *,
    versiones_definicion_local: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Compara la plantilla global actual con la copia local vigente del tenant."""
    versiones_definicion_local = versiones_definicion_local or {}
    plantilla = _idx_por_global(lineas_plantilla)
    local = _idx_por_global(lineas_local)
    cambios: list[dict[str, Any]] = []

    for gid, pl in plantilla.items():
        loc = local.get(gid)
        v_dest = int(pl.get("version_definicion") or pl.get("version") or 0)
        grupo = str(pl["tipo_sujeto_aplicable"])
        if loc is None:
            cambios.append({
                "tipo": "agregado",
                "grupo": grupo,
                "nombre": pl["nombre"],
                "version_origen": 0,
                "version_destino": v_dest,
                "definicion_global_id": gid,
                "requisito_definicion_id": None,
                "clasificacion_destino": pl["clasificacion"],
                "bloqueante_durante_ejecucion_destino": pl["bloqueante_durante_ejecucion"],
            })
            continue
        v_origen = versiones_definicion_local.get(str(loc.get("requisito_definicion_id")), v_dest)
        rid = str(loc["requisito_definicion_id"])
        if pl["clasificacion"] == "bloqueante_duro" and loc["clasificacion"] == "excepcionable":
            cambios.append({
                "tipo": "pasa_a_bloquear",
                "grupo": grupo,
                "nombre": pl["nombre"],
                "version_origen": v_origen,
                "version_destino": v_dest,
                "definicion_global_id": gid,
                "requisito_definicion_id": rid,
                "clasificacion_destino": pl["clasificacion"],
                "bloqueante_durante_ejecucion_destino": pl["bloqueante_durante_ejecucion"],
            })
        elif pl["clasificacion"] == "excepcionable" and loc["clasificacion"] == "bloqueante_duro":
            cambios.append({
                "tipo": "deja_de_bloquear",
                "grupo": grupo,
                "nombre": pl["nombre"],
                "version_origen": v_origen,
                "version_destino": v_dest,
                "definicion_global_id": gid,
                "requisito_definicion_id": rid,
                "clasificacion_destino": pl["clasificacion"],
                "bloqueante_durante_ejecucion_destino": pl["bloqueante_durante_ejecucion"],
            })

    for gid, loc in local.items():
        if gid not in plantilla:
            cambios.append({
                "tipo": "quitado",
                "grupo": str(loc.get("tipo_sujeto_aplicable") or "persona"),
                "nombre": loc["nombre"],
                "version_origen": versiones_definicion_local.get(str(loc.get("requisito_definicion_id")), 0),
                "version_destino": 0,
                "definicion_global_id": gid,
                "requisito_definicion_id": str(loc["requisito_definicion_id"]),
                "clasificacion_destino": None,
                "bloqueante_durante_ejecucion_destino": None,
            })

    return sorted(cambios, key=lambda c: (c["grupo"], c["nombre"], c["tipo"]))
