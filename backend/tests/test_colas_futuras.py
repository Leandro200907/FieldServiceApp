"""Contrato v1 de las colas sin implementación (`evidencia_qr`): NINGÚN flujo soportado
las produce. Relevamiento (2026-09-19, actualizado Fase 2 punto 2):

| cola                  | productor en app/ | comando/evento que la encola |
|-----------------------|-------------------|------------------------------|
| evidencia_qr          | ninguno           | el QR del paquete se genera al vuelo en GET /publico/paquete/{token}/qr.png (no necesita cola) |
| score_documental      | score/servicio.encolar_snapshot_diario (reloj) | snapshot diario del score (handler_score_documental) |
| validacion_evidencia  | storage/servicio.confirmar_subida | verificación técnica del archivo (handler_validacion_evidencia, Fase 2 punto 2) |
| notificaciones        | alertas/servicio (entregar_notificaciones, avisar_oc_sin_matriz); requisitos/plantillas.control_plantillas; worker/outbox (alerta de estancado); modules/evidencia/servicio (aviso caso B y dead-letter) | `AlertasDeVencimiento` (coalescido), `OcSinMatriz`, `PlantillaGlobalActualizada`, `OutboxEstancado`, `EvidenciaInvalida`, `ValidacionEvidenciaEstancada` |
| drenaje_outbox        | (la vuelta del worker drena directo) | — |

Si alguien agrega un productor de una cola futura, el test falla y obliga a implementar
el handler (o a desactivar el productor) antes de liberar."""
from __future__ import annotations

import re
from pathlib import Path

from app.worker import main as worker_main
from app.worker.cola import COLAS

RAIZ = Path(__file__).resolve().parents[1]
FUTURAS = ("evidencia_qr",)
SOPORTADAS = ("notificaciones", "drenaje_outbox", "score_documental", "validacion_evidencia")


def _productores(cola: str) -> list[str]:
    """Archivos de app/ que encolan en `cola` (llamadas a encolar(...) con esa cola)."""
    hallados = []
    for archivo in (RAIZ / "app").rglob("*.py"):
        if "worker" in archivo.parts and archivo.name in ("cola.py", "main.py"):
            continue  # la propia cola y el loop no son productores
        texto = archivo.read_text(encoding="utf-8")
        if re.search(rf"encolar\([^)]*[\"']{cola}[\"']", texto, re.S):
            hallados.append(str(archivo.relative_to(RAIZ)))
    return hallados


def test_ningun_flujo_soportado_produce_colas_futuras():
    assert set(FUTURAS) | set(SOPORTADAS) == set(COLAS)
    for cola in FUTURAS:
        assert _productores(cola) == [], f"{cola} tiene productor: implementar handler o desactivar el productor"
    assert sorted(Path(p).as_posix() for p in _productores("notificaciones")) == [
        "app/modules/alertas/servicio.py", "app/modules/evidencia/servicio.py",
        "app/modules/operadoras/servicio.py", "app/modules/requisitos/plantillas.py",
        "app/worker/outbox.py"]
    assert sorted(Path(p).as_posix() for p in _productores("validacion_evidencia")) == ["app/storage/servicio.py"]
    assert set(worker_main.HANDLERS) == set(SOPORTADAS)   # las futuras sólo tienen handler_no_implementado
