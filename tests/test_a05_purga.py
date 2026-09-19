"""A-05 de la auditoría — verificación explícita de la purga en dos fases
(`app/worker/procesos_reloj.py::control_retencion`).
"""
from __future__ import annotations

import threading
from datetime import timedelta

from sqlalchemy import text

from app.comun.reloj import ahora_utc
from app.db import tenant_session
from app.worker.procesos_reloj import control_retencion
from tests.test_robustez import _en_paralelo
from tests.test_worker import _StorageFalso, _contar_eventos, _estado_archivo, _preparar_retencion


def _preparar(t) -> tuple[str, str]:
    with tenant_session(t) as s:
        viejo = _preparar_retencion(s, t)
    return viejo, f"{t}/{viejo}/viejo.pdf"


def test_purga_pendiente_se_confirma_antes_del_borrado_y_sin_transaccion_abierta(tenant_de_prueba):
    """Dentro de `borrar()`: (a) la fila ya dice `purga_pendiente` leída desde OTRA sesión —es
    decir, commiteada—; (b) no hay ninguna sesión del rol de app 'idle in transaction'
    (la lectura de pendientes se cerró antes del I/O)."""
    t = tenant_de_prueba.tenant_id
    viejo, clave = _preparar(t)
    vistos: dict = {}

    class _Espia(_StorageFalso):
        def borrar(self, clave_):
            vistos["estado"] = _estado_archivo(t, viejo)
            with tenant_session(t) as s:
                vistos["idle_in_tx"] = s.execute(text(
                    "SELECT count(*) FROM pg_stat_activity WHERE usename = current_user AND pid <> pg_backend_pid() "
                    "AND state = 'idle in transaction'")).scalar()
                vistos["lock_libre"] = s.execute(text(
                    "SELECT 1 FROM modulo1.documento WHERE documento_id = :d FOR UPDATE NOWAIT"), {"d": viejo}).scalar()
            return super().borrar(clave_)

    control_retencion(t, _Espia(confirma=True), ahora_utc())
    assert vistos["estado"] == ("purga_pendiente", clave)
    assert vistos["idle_in_tx"] == 0
    assert vistos["lock_libre"] == 1  # nadie tenía la fila bloqueada durante el I/O
    assert _estado_archivo(t, viejo) == ("purgado", None)


def test_error_real_del_backend_deja_pendiente_y_reintentable_nunca_purgado(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    viejo, clave = _preparar(t)

    class _Explota(_StorageFalso):
        def borrar(self, clave_):
            self.borradas.append(clave_)
            raise IOError("bucket inaccesible")

    st = _Explota(confirma=False, presentes={clave})  # el archivo sigue existiendo
    for _ in range(3):
        r = control_retencion(t, st, ahora_utc())
        assert r["purgados"] == 0 and r["no_confirmados"] == 1
        assert _estado_archivo(t, viejo) == ("purga_pendiente", clave)
    assert len(st.borradas) == 3  # se reintenta en cada vuelta
    with tenant_session(t) as s:
        assert _contar_eventos(s, "ArchivoPurgado") == 0
    # cuando el backend vuelve, se completa
    assert control_retencion(t, _StorageFalso(confirma=True), ahora_utc())["purgados"] == 1
    assert _estado_archivo(t, viejo) == ("purgado", None)


def test_archivo_inexistente_se_trata_idempotentemente_como_borrado(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    viejo, clave = _preparar(t)
    # backend que responde "no confirmo" (p. ej. 404) pero el archivo no existe
    st = _StorageFalso(confirma=False, presentes=set())
    r = control_retencion(t, st, ahora_utc())
    assert r["purgados"] == 1 and _estado_archivo(t, viejo) == ("purgado", None)
    with tenant_session(t) as s:
        assert _contar_eventos(s, "ArchivoPurgado") == 1
    # segunda vuelta: nada que hacer, sin evento duplicado
    assert control_retencion(t, st, ahora_utc())["candidatos"] == 0
    with tenant_session(t) as s:
        assert _contar_eventos(s, "ArchivoPurgado") == 1


def test_caida_despues_del_borrado_y_antes_de_confirmar_se_reconcilia(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    viejo, clave = _preparar(t)
    presentes = {clave}

    class _MuereTrasBorrar(_StorageFalso):
        def borrar(self, clave_):
            presentes.discard(clave_)
            raise RuntimeError("proceso caído después del unlink")

    r1 = control_retencion(t, _MuereTrasBorrar(confirma=True, presentes=presentes), ahora_utc())
    # el archivo ya no está: la misma vuelta reconcilia (o la siguiente, si el proceso murió del todo)
    assert r1["purgados"] == 1 and _estado_archivo(t, viejo) == ("purgado", None)
    with tenant_session(t) as s:
        assert _contar_eventos(s, "ArchivoPurgado") == 1


def test_dos_workers_en_paralelo_no_purgan_dos_veces(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    viejo, clave = _preparar(t)
    barrera = threading.Barrier(2)
    presentes = {clave}

    class _Lento(_StorageFalso):
        def borrar(self, clave_):
            barrera.wait(timeout=10)  # ambos workers llegan al I/O a la vez
            presentes.discard(clave_)
            return True

    st = _Lento(confirma=True, presentes=presentes)
    salidas = _en_paralelo([lambda: control_retencion(t, st, ahora_utc())] * 2)
    assert all(e is None for _, e in salidas), [str(e) for _, e in salidas if e]
    assert sum(r["purgados"] for r, _ in salidas) == 1  # exactamente una confirmación
    assert _estado_archivo(t, viejo) == ("purgado", None)
    with tenant_session(t) as s:
        assert _contar_eventos(s, "ArchivoPurgado") == 1


def test_evidencia_de_auditoria_sin_contenido(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    viejo, clave = _preparar(t)
    control_retencion(t, _StorageFalso(confirma=True), ahora_utc())
    with tenant_session(t) as s:
        p = s.execute(text("SELECT payload FROM modulo1.event_log WHERE tipo = 'ArchivoPurgado'")).scalar()
        purgado_en = s.execute(text("SELECT archivo_purgado_en FROM modulo1.documento WHERE documento_id = :d"), {"d": viejo}).scalar()
    assert p["documento_id"] == viejo and p["clave_storage"] == clave
    assert p["motivo"] == "plazo_retencion_archivo vencido" and p["plazo_retencion"] == "30 days"
    assert p["estado_version"] == "sucedida" and p["requisito_definicion_id"] and p["creado_en"]
    assert p["checksum_sha256"] == "ck" and p["bytes"] == 1  # referencia verificable
    assert p["purgado_en"] and purgado_en is not None
    assert p["usuario_id"] == "sistema"
    assert "contenido" not in p and "base64" not in str(p)
