"""Contrato v1 de las colas sin implementación (`evidencia_qr`): NINGÚN flujo soportado
las produce. Relevamiento (2026-09-19, actualizado Fase 2 punto 2):

| cola                  | productor en app/ | comando/evento que la encola |
|-----------------------|-------------------|------------------------------|
| evidencia_qr          | ninguno           | el QR del paquete se genera al vuelo en GET /publico/paquete/{token}/qr.png (no necesita cola) |
| score_documental      | score/servicio.encolar_snapshot_diario (reloj) | snapshot diario del score (handler_score_documental) |
| validacion_evidencia  | storage/servicio.confirmar_subida | verificación técnica del archivo (handler_validacion_evidencia, Fase 2 punto 2) |
| notificaciones        | alertas/servicio (entregar_notificaciones, avisar_oc_sin_matriz); requisitos/plantillas.control_plantillas; worker/outbox (alerta de estancado); modules/evidencia/servicio (aviso caso B y dead-letter) | `AlertasDeVencimiento` (coalescido), `OcSinMatriz`, `PlantillaGlobalActualizada`, `OutboxEstancado`, `EvidenciaInvalida`, `ValidacionEvidenciaEstancada` |
| drenaje_outbox        | (la vuelta del worker drena directo) | — |

Si alguien agrega un productor de una cola futura, el primer test falla y obliga a
implementar el handler (o a desactivar el productor) antes de liberar. El E2E principal
termina con cero jobs en dead-letter."""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import text

from app.db import tenant_session
from app.worker import main as worker_main
from app.worker.cola import COLAS
from app.worker.outbox import PublicadorEnMemoria

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
        "app/modules/requisitos/plantillas.py", "app/worker/outbox.py"]
    assert sorted(Path(p).as_posix() for p in _productores("validacion_evidencia")) == ["app/storage/servicio.py"]
    assert set(worker_main.HANDLERS) == set(SOPORTADAS)   # las futuras sólo tienen handler_no_implementado


def test_e2e_principal_termina_sin_jobs_obligatorios_en_dead_letter(cliente_api, tenant_de_prueba):
    """Corre el flujo E2E completo por HTTP y después una vuelta real del worker: ningún
    job del tenant queda `fallido` y ninguno pertenece a una cola futura."""
    from tests.test_e2e_http import test_flujo_completo_por_http

    class _Storage:
        def clave_para(self, *a): return "x"
        def existe(self, c): return False
        def inspeccionar(self, c): return None
        def borrar(self, c): return True
        def disponible(self): return True

    test_flujo_completo_por_http(cliente_api, tenant_de_prueba)
    worker_main.correr_una_vuelta(_Storage(), PublicadorEnMemoria())
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        filas = s.execute(text("SELECT cola, estado, count(*) FROM modulo1.job_queue WHERE tenant_id = :t GROUP BY 1, 2"),
                          {"t": tenant_de_prueba.tenant_id}).all()
    assert all(estado != "fallido" for _, estado, _ in filas), filas
    assert all(cola not in FUTURAS for cola, _, _ in filas), filas
