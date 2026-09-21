"""Control de vencimientos — función PURA (modelo-dominio 2.3): legajos + fecha de hoy →
qué umbral cruza cada requisito. Sin I/O. Todo lo que tiene efecto (abrir, notificar,
escalar, marcar no habilitado) es política que reacciona a lo que esto devuelve
(`app/modules/alertas/servicio.py`).

`etapa` es una función determinística de `vigente_hasta - hoy` y de la parametrización
(especificación 4.6): avanza sola con el tiempo, sin importar `estado`.

    T - plazo      → aviso
    T - plazo/2    → recordatorio
    T + 1 (vencido: vigente_hasta es inclusive, 6.1) → vencido
    T + N + 1      → escalado
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

ETAPAS = ("aviso", "recordatorio", "vencido", "escalado")
ORDEN_ETAPA = {e: i for i, e in enumerate(ETAPAS)}


@dataclass(frozen=True)
class ParametrosAlerta:
    plazo_aviso_dias: int = 30
    escalamiento_dias: int = 7
    rol_escalamiento: str = "responsable_legajos"
    reconocimiento_dias: int = 3


def etapa_de(vigente_hasta: date, hoy: date, p: ParametrosAlerta) -> str | None:
    """None: todavía no cruzó el primer umbral (no hay alerta)."""
    dias = (vigente_hasta - hoy).days  # > 0 faltan días; 0 vence hoy (aún vigente); < 0 vencido
    if dias < -p.escalamiento_dias:
        return "escalado"
    if dias < 0:
        return "vencido"
    if dias <= p.plazo_aviso_dias // 2:
        return "recordatorio"
    if dias <= p.plazo_aviso_dias:
        return "aviso"
    return None


def avanza(etapa_actual: str, etapa_nueva: str | None) -> bool:
    """La etapa solo avanza (nunca retrocede aunque cambie la parametrización)."""
    return etapa_nueva is not None and ORDEN_ETAPA[etapa_nueva] > ORDEN_ETAPA[etapa_actual]


def destinatarios_de(etapa: str, p: ParametrosAlerta) -> tuple[list[str], str]:
    """(roles a notificar, prioridad) al cruzar la etapa (modelo-dominio 2.4)."""
    if etapa in ("aviso", "recordatorio"):
        return ["tecnico", "supervisor", "responsable_legajos"], "normal"
    if etapa == "vencido":
        return ["supervisor", "responsable_legajos", "tecnico"], "alta"
    return [p.rol_escalamiento], "alta"
