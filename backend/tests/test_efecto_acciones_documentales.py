"""E-79–E-81: etiquetas y fecha de bloqueo en acciones pendientes."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.core.consulta_documental import efecto_accion_documental, fecha_desde_cuando_bloquea


def _oc(desde: str = "2026-09-01", hasta: str = "2026-11-03") -> dict:
    return {"vigencia_desde": date.fromisoformat(desde), "vigencia_hasta": date.fromisoformat(hasta)}


def test_e79_rechazo_operadora_ya_bloquea_sin_usar_vencimiento_apto():
    hoy = date(2026, 10, 4)
    req = {
        "es_rechazo_operadora": True,
        "motivo": "Rechazado por Vista el 04/10/2026",
        "rechazado_en": datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc),
        "primer_quiebre": date(2027, 2, 7),
        "vigente_hasta": date(2027, 2, 6),
        "estado": "faltante",
    }
    fb = fecha_desde_cuando_bloquea(hoy, _oc(), req, date(2026, 9, 1))
    assert fb == date(2026, 10, 4)
    assert efecto_accion_documental(hoy, _oc(), req, date(2026, 9, 1)) == "Rechazado por Vista · Ya bloquea"


def test_e80_licencia_por_vencer_bloquea_dia_siguiente():
    hoy = date(2026, 10, 4)
    req = {
        "estado": "vence_durante_periodo",
        "vigente_hasta": date(2026, 10, 24),
        "evidencia_id": "doc-lic",
    }
    assert efecto_accion_documental(hoy, _oc(), req, date(2026, 9, 1)) == "Por vencer · Bloquea desde 25/10/2026"


def test_e81_pendiente_revision_sin_respaldo():
    hoy = date(2026, 10, 4)
    req = {
        "estado": "pendiente_revision",
        "archivo_validacion": "pendiente",
        "evidencia_id": "doc-juan",
    }
    assert efecto_accion_documental(hoy, _oc(), req, date(2026, 9, 1)) == "Sin respaldo válido · Ya bloquea"
