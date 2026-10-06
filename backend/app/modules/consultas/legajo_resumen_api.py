"""Campos agregados de legajo para que el front no recalcule dominio (regla 15)."""
from __future__ import annotations

from datetime import date
from typing import Any


def item_pendiente_revision(item: dict[str, Any]) -> bool:
    if item.get("propuesta_en_revision"):
        return True
    codigos = [item.get("estado_presentacion"), *(item.get("estados_adicionales") or [])]
    return any(c in ("propuesta_en_revision", "archivo_en_revision") for c in codigos if c)


def enriquecer_resumen_legajo_exigidos(items: list[dict[str, Any]], resumen: dict[str, Any]) -> None:
    """Solo requisitos exigidos por backlog (misma regla que tarjetas E-101)."""
    exigidos = [i for i in items if i.get("exigido_backlog") and not i.get("no_exigido_backlog")]
    resumen["pendientes_revision"] = sum(1 for i in exigidos if item_pendiente_revision(i))
    proximos: list[str] = []
    for i in exigidos:
        if i.get("estado_presentacion") == "sin_documento":
            continue
        if i.get("vencido"):
            continue
        dias = i.get("dias_para_vencer")
        if dias is not None and dias < 0:
            continue
        vh = i.get("vigente_hasta")
        if vh:
            proximos.append(str(vh)[:10])
    resumen["proximo_vencimiento"] = min(proximos) if proximos else None


def tarjeta_exigido_de_item(item: dict[str, Any], hoy: date, plazo_aviso: int) -> str | None:
    if not item.get("exigido_backlog") or item.get("no_exigido_backlog"):
        return None
    from app.modules.consultas.ficha_legajo import bucket_tarjeta_exigido_desde_agregado

    hasta_raw = item.get("vigente_hasta")
    hasta: date | None = None
    if hasta_raw:
        hasta = date.fromisoformat(str(hasta_raw)[:10])
    vencido = bool(item.get("vencido"))
    if hasta is not None and not vencido:
        vencido = hasta < hoy
    evidencia_id = None if str(item.get("id", "")).startswith("exigido-") else item.get("id")
    return bucket_tarjeta_exigido_desde_agregado(
        evidencia_id=str(evidencia_id) if evidencia_id else None,
        archivo_validacion=item.get("archivo_validacion"),
        vigente_hasta=hasta,
        hoy=hoy,
        plazo_aviso=plazo_aviso,
        vencido_calendario=vencido,
    )
