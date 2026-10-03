"""Vigencia y estado de respaldo como dimensiones separadas."""
from __future__ import annotations

from datetime import date

from app.modules.consultas.presentacion_evidencia import enriquecer_fila_evidencia


def test_vencida_con_archivo_invalido_expone_dos_estados():
    hoy = date(2026, 9, 18)
    fila = {
        "estado_confirmacion": "verificado",
        "vigente_desde": date(2024, 1, 1),
        "vigente_hasta": date(2025, 1, 1),
        "archivo_estado": "confirmado",
        "archivo_validacion": "invalido",
        "clave_storage": "tenant/doc/demo.pdf",
        "plazo_aviso_dias": 30,
        "vencido": True,
    }
    item = enriquecer_fila_evidencia(fila, hoy, 30)
    assert item["estado_presentacion"] == "vencida"
    assert item["estados_adicionales"] == ["evidencia_invalida"]


def test_declarado_por_vencer_expone_vigencia_y_confirmacion_aparte():
    hoy = date(2026, 9, 18)
    fila = {
        "estado_confirmacion": "declarado",
        "vigente_desde": date(2026, 7, 1),
        "vigente_hasta": date(2026, 10, 8),
        "archivo_estado": "confirmado",
        "archivo_validacion": "pendiente",
        "clave_storage": "tenant/doc/demo.pdf",
        "plazo_aviso_dias": 30,
        "vencido": False,
    }
    item = enriquecer_fila_evidencia(fila, hoy, 30)
    assert item["estado_presentacion"] == "por_vencer"
    assert item["estados_adicionales"] == ["archivo_en_revision", "declarada"]
