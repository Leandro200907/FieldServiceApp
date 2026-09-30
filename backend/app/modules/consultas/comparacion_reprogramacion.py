"""Comparación documental antes/después de reprogramar una OC (D-E)."""
from __future__ import annotations

from typing import Any

_ETIQUETA = {"persona": "técnicos", "vehiculo": "vehículos", "equipo": "equipos", "empresa": "empresa"}


def _count_vencimientos_en_ventana(ev: dict[str, Any]) -> int:
    total = 0
    for d in ev.get("disponibilidad_por_tipo") or []:
        if d.get("estado") == "fuera_de_alcance":
            continue
        total += len(d.get("se_cae_en_ventana") or [])
    return total


def _tiene_alerta(ev: dict[str, Any], codigo: str, tipo_sujeto: str | None = None) -> bool:
    for a in ev.get("alertas_ciertas") or []:
        if a.get("codigo") != codigo:
            continue
        if tipo_sujeto is not None and a.get("tipo_sujeto") != tipo_sujeto:
            continue
        return True
    return False


def comparar_efecto_documental(antes: dict[str, Any], despues: dict[str, Any]) -> dict[str, Any]:
    mensajes: list[str] = []
    cae_a = _count_vencimientos_en_ventana(antes)
    cae_d = _count_vencimientos_en_ventana(despues)
    if cae_d > cae_a:
        n = cae_d - cae_a
        mensajes.append(f"aparecen {n} vencimiento{'s' if n != 1 else ''} dentro de la ventana")
    elif cae_d < cae_a:
        n = cae_a - cae_d
        mensajes.append(f"desaparecen {n} vencimiento{'s' if n != 1 else ''} dentro de la ventana")

    if _tiene_alerta(antes, "empresa_no_habilitada") and not _tiene_alerta(despues, "empresa_no_habilitada"):
        mensajes.append("se resuelve el incumplimiento de empresa en la ventana")
    elif not _tiene_alerta(antes, "empresa_no_habilitada") and _tiene_alerta(despues, "empresa_no_habilitada"):
        mensajes.append("aparece incumplimiento de empresa en la ventana")

    if _tiene_alerta(antes, "sin_matriz") and not _tiene_alerta(despues, "sin_matriz"):
        mensajes.append("se resuelve la falta de matriz aplicable")
    elif not _tiene_alerta(antes, "sin_matriz") and _tiene_alerta(despues, "sin_matriz"):
        mensajes.append("aparece falta de matriz aplicable en la ventana")

    for tipo in ("vehiculo", "persona", "equipo"):
        if _tiene_alerta(antes, "tipo_sin_habilitados", tipo) and not _tiene_alerta(despues, "tipo_sin_habilitados", tipo):
            mensajes.append(f"se resuelve el faltante de {_ETIQUETA.get(tipo, tipo)}")
        elif not _tiene_alerta(antes, "tipo_sin_habilitados", tipo) and _tiene_alerta(despues, "tipo_sin_habilitados", tipo):
            mensajes.append(f"aparece faltante de {_ETIQUETA.get(tipo, tipo)} en la ventana")

    if antes.get("tiene_alertas") and not despues.get("tiene_alertas"):
        mensajes.append("se resuelven todas las alertas ciertas")
    elif not antes.get("tiene_alertas") and despues.get("tiene_alertas"):
        mensajes.append("aparecen alertas ciertas en la nueva ventana")

    return {
        "documental_anterior": antes,
        "documental_nuevo": despues,
        "mensajes": mensajes,
        "tiene_alertas_antes": bool(antes.get("tiene_alertas")),
        "tiene_alertas_despues": bool(despues.get("tiene_alertas")),
    }
