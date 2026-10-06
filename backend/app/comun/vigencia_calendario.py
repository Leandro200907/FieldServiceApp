"""Campos de vigencia por calendario (inclusive en ambos bordes). Fuente única para consultas."""
from __future__ import annotations

from datetime import date
from typing import Any


def campos_vigencia_en_fecha(
    vigente_desde: date,
    vigente_hasta: date | None,
    hoy: date,
) -> dict[str, bool | int | None]:
    vigente_hoy = vigente_desde <= hoy and (vigente_hasta is None or hoy <= vigente_hasta)
    dias_para_vencer = (vigente_hasta - hoy).days if vigente_hasta is not None else None
    vencido = vigente_hasta is not None and vigente_hasta < hoy
    return {
        "vigente_hoy": vigente_hoy,
        "dias_para_vencer": dias_para_vencer,
        "vencido": vencido,
    }


def aplicar_campos_vigencia_a_fila(fila: dict[str, Any], hoy: date) -> dict[str, Any]:
    """Mutación in-place sobre copia: exige `vigente_desde` y opcional `vigente_hasta` como date."""
    desde: date = fila["vigente_desde"]
    hasta: date | None = fila.get("vigente_hasta")
    fila.update(campos_vigencia_en_fecha(desde, hasta, hoy))
    return fila
