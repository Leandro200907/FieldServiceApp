"""Worker contra base real: cola SKIP LOCKED con lease, outbox, procesos de reloj y
listar_tenants(). Datos insertados por SQL dentro de tenant_session."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import text

from tests import apoyo

from app.comun.eventos import encolar_outbox
from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.db import SessionLocal, platform_session, tenant_session
from app.worker import main as worker_main
from app.worker.cola import completar, encolar, fallar, tomar
from app.worker.outbox import PublicadorEnMemoria, drenar_outbox
from app.worker.procesos_reloj import control_retencion, control_vencimientos, vencer_excepciones_y_constancias


def _sesion_manual(tenant_id: str):
    """Sesión sin commit automático, para simular dos workers concurrentes."""
    s = SessionLocal()
    s.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
    return s


def _contar_eventos(s, tipo: str) -> int:
    return s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = :t"), {"t": tipo}).scalar()


def _definicion(s, tenant_id: str, retencion: str | None = None, categoria: str = "documento") -> str:
    rid = str(uuid.uuid4())
    s.execute(
        text(
            "INSERT INTO modulo1.definicion_requisito (requisito_definicion_id, tenant_id, nombre, categoria, "
            "tipo_sujeto_aplicable, plazo_retencion_archivo) VALUES (:r, :t, :n, :c, 'persona', CAST(:p AS interval))"
        ),
        {"r": rid, "t": tenant_id, "n": f"req-{rid[:8]}", "c": categoria, "p": retencion},
    )
    return rid


def _documento(s, tenant_id: str, requisito_id: str, vigente_hasta, estado_version="vigente", clave=None, creado_en=None) -> str:
    # Un sujeto distinto por documento: uq_documento_vigente admite un solo vigente por (sujeto, requisito).
    did = str(uuid.uuid4())
    apoyo.legajo(s, tenant_id, f"persona_{did[:8]}")
    s.execute(
        text(
            "INSERT INTO modulo1.documento (documento_id, tenant_id, sujeto_id, requisito_definicion_id, vigente_desde, "
            "vigente_hasta, origen, estado_version, clave_storage, archivo_estado, checksum_archivo, archivo_bytes, creado_en) "
            "VALUES (:d, :t, :sj, :r, :desde, :hasta, 'carga_manual', :ev, :clave, "
            "CASE WHEN CAST(:clave AS text) IS NULL THEN 'sin_archivo' ELSE 'confirmado' END, "
            "CASE WHEN CAST(:clave AS text) IS NULL THEN NULL ELSE 'ck' END, CASE WHEN CAST(:clave AS text) IS NULL THEN NULL ELSE 1 END, "
            "COALESCE(:creado, now()))"
        ),
        {"d": did, "t": tenant_id, "sj": f"persona_{did[:8]}", "r": requisito_id, "desde": vigente_hasta - timedelta(days=365), "hasta": vigente_hasta,
         "ev": estado_version, "clave": (clave.replace("{doc}", did) if clave else None), "creado": creado_en},
    )
    return did


# --- cola -------------------------------------------------------------------------
def test_skip_locked_dos_workers_reciben_jobs_distintos(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    with tenant_session(t) as s:
        j1 = encolar(s, "notificaciones", {"n": 1}, tenant_id=t)
        j2 = encolar(s, "notificaciones", {"n": 2}, tenant_id=t)
    a, b = _sesion_manual(t), _sesion_manual(t)
    try:
        ja = tomar(a, "notificaciones", lease_seg=60)  # queda lockeado, sin commit
        jb = tomar(b, "notificaciones", lease_seg=60)
        assert ja is not None and jb is not None
        assert {ja.id, jb.id} == {j1, j2}
        assert ja.estado == "en_curso" and ja.intentos == 1
        a.commit()
        b.commit()
    finally:
        a.close()
        b.close()
    # Mientras el lease vive nadie los vuelve a tomar.
    with tenant_session(t) as s:
        assert tomar(s, "notificaciones") is None


def test_lease_vencido_permite_retomar_y_lease_obligatorio(tenant_de_prueba):
    import pytest

    t = tenant_de_prueba.tenant_id
    with tenant_session(t) as s:
        jid = encolar(s, "evidencia_qr", {"x": 1}, tenant_id=t)
        assert tomar(s, "evidencia_qr", lease_seg=30).id == jid
        assert tomar(s, "evidencia_qr") is None
        with pytest.raises(ValueError):
            tomar(s, "evidencia_qr", lease_seg=0)
    # Simula worker caído: el lease ya pasó.
    with tenant_session(t) as s:
        s.execute(text("UPDATE modulo1.job_queue SET lease_hasta = now() - interval '1 minute' WHERE id = :id"), {"id": jid})
    with tenant_session(t) as s:
        job = tomar(s, "evidencia_qr", lease_seg=30)
        assert job is not None and job.id == jid and job.intentos == 2
        completar(s, jid, job.lease_token)
    with tenant_session(t) as s:
        assert s.execute(text("SELECT estado FROM modulo1.job_queue WHERE id = :id"), {"id": jid}).scalar() == "completado"


def test_fallar_reintenta_con_backoff_y_pasa_a_fallido(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    with tenant_session(t) as s:
        jid = encolar(s, "score_documental", {}, tenant_id=t)
        j = tomar(s, "score_documental")
        assert fallar(s, jid, j.lease_token, max_intentos=3) == "pendiente"
        fila = s.execute(text("SELECT estado, disponible_en > now() FROM modulo1.job_queue WHERE id = :id"), {"id": jid}).first()
        assert fila[0] == "pendiente" and fila[1] is True  # backoff: no disponible todavía
        assert tomar(s, "score_documental") is None
        s.execute(text("UPDATE modulo1.job_queue SET disponible_en = now() WHERE id = :id"), {"id": jid})
        j = tomar(s, "score_documental")
        assert fallar(s, jid, j.lease_token, reintentar_en_seg=0, max_intentos=3) == "pendiente"
        j = tomar(s, "score_documental")  # intentos = 3
        assert fallar(s, jid, j.lease_token, max_intentos=3) == "fallido"
        assert s.execute(text("SELECT estado FROM modulo1.job_queue WHERE id = :id"), {"id": jid}).scalar() == "fallido"
        assert tomar(s, "score_documental") is None


def test_job_de_sistema_sin_tenant_es_visible(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    with tenant_session(t) as s:
        jid = encolar(s, "validacion_evidencia", {"sistema": True})
        job = tomar(s, "validacion_evidencia")
        assert job is not None and job.id == jid and job.tenant_id is None
        completar(s, jid, job.lease_token)


# --- outbox -----------------------------------------------------------------------
def test_outbox_drena_marca_procesado_e_idempotente(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    pub = PublicadorEnMemoria()
    with tenant_session(t) as s:
        encolar_outbox(s, t, "HabilitacionRequiereRevaluacion", {"commitment_id": "OC-1", "motivo": "test"})
        encolar_outbox(s, t, "CumplimientoEmpresaAfectado", {"empresa": "x"})
    with tenant_session(t) as s:
        assert drenar_outbox(s, t, pub) == 2
    assert {e[0] for e in pub.eventos} == {"HabilitacionRequiereRevaluacion", "CumplimientoEmpresaAfectado"}
    assert any(e[1].get("commitment_id") == "OC-1" for e in pub.eventos)
    with tenant_session(t) as s:
        assert drenar_outbox(s, t, pub) == 0  # segunda vuelta: nada nuevo
        assert s.execute(text("SELECT count(*) FROM modulo1.outbox_events WHERE procesado_en IS NULL")).scalar() == 0
    assert len(pub.eventos) == 2


def test_outbox_publicador_falla_deja_pendiente_y_cuenta_intento(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    with tenant_session(t) as s:
        encolar_outbox(s, t, "CumplimientoEmpresaAfectado", {"empresa": "x"})
    with tenant_session(t) as s:
        assert drenar_outbox(s, t, PublicadorEnMemoria(fallar_con=RuntimeError("caído"))) == 0
    with tenant_session(t) as s:
        fila = s.execute(text("SELECT procesado_en, intentos FROM modulo1.outbox_events")).first()
        assert fila[0] is None and fila[1] == 1
        assert drenar_outbox(s, t, PublicadorEnMemoria()) == 1


# --- procesos de reloj ---------------------------------------------------------------
def test_control_vencimientos_abre_alerta_una_sola_vez(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    ahora = ahora_utc()
    with tenant_session(t) as s:
        hoy = hoy_del_tenant(s, t, ahora)
        req = _definicion(s, t)
        pronto = _documento(s, t, req, hoy + timedelta(days=10))
        vencido = _documento(s, t, req, hoy - timedelta(days=1))
        _documento(s, t, req, hoy + timedelta(days=200))  # lejos: sin alerta
        _documento(s, t, req, hoy + timedelta(days=5), estado_version="sucedida")  # no vigente: sin alerta
    with tenant_session(t) as s:
        r = control_vencimientos(s, t, ahora)
        assert r["alertas_abiertas"] == 2
    with tenant_session(t) as s:
        assert control_vencimientos(s, t, ahora)["alertas_abiertas"] == 0  # idempotente
        assert _contar_eventos(s, "AlertaDeVencimientoAbierta") == 2
        ids = {f[0] for f in s.execute(text("SELECT payload->>'documento_id' FROM modulo1.event_log WHERE tipo = 'AlertaDeVencimientoAbierta'"))}
        assert ids == {pronto, vencido}
        assert s.execute(text("SELECT count(*) FROM modulo1.job_queue WHERE cola = 'notificaciones' AND estado = 'pendiente'")).scalar() == 2
        vencidos = s.execute(text("SELECT payload->>'vencido' FROM modulo1.event_log WHERE tipo = 'AlertaDeVencimientoAbierta' AND payload->>'documento_id' = :d"), {"d": vencido}).scalar()
        assert vencidos == "true"
        latido = s.execute(text("SELECT ultimo_ok, detalle FROM modulo1.latido_proceso WHERE nombre = 'control_vencimientos' AND tenant_id = :t"), {"t": t}).first()
        assert latido is not None and latido[0] is not None and latido[1]["alertas_abiertas"] == 0
    # Resuelta → se puede reabrir.
    with tenant_session(t) as s:
        s.execute(text("INSERT INTO modulo1.event_log (tenant_id, tipo, payload) VALUES (:t, 'AlertaResuelta', CAST(:p AS jsonb))"), {"t": t, "p": f'{{"documento_id": "{pronto}"}}'})
    with tenant_session(t) as s:
        assert control_vencimientos(s, t, ahora)["alertas_abiertas"] == 1


def test_vencer_excepciones_y_constancias(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    ahora = ahora_utc()
    with tenant_session(t) as s:
        hoy = hoy_del_tenant(s, t, ahora)
        req = _definicion(s, t)
        apoyo.legajo(s, t, "p1")
        ref = apoyo.evaluacion(s, t, "OC-9")
        for vig, estado in ((hoy - timedelta(days=1), "otorgada"), (hoy, "otorgada"), (hoy - timedelta(days=5), "revocada")):
            s.execute(
                text(
                    "INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, "
                    "commitment_id, otorgada_por, motivo, vigencia, estado) VALUES (:t, :ref, 'p1', :r, 'OC-9', 'sup', 'm', :v, :e)"
                ),
                {"t": t, "ref": ref, "r": req, "v": vig, "e": estado},
            )
        s.execute(
            text(
                "INSERT INTO modulo1.constancia_cliente (tenant_id, sujeto_id, requisito_definicion_id, cliente_id, commitment_id, "
                "registrada_por, evidencia, vigencia) VALUES (:t, 'p1', :r, gen_random_uuid(), NULL, 'rl', 'ev', :v)"
            ),
            {"t": t, "r": req, "v": hoy - timedelta(days=2)},
        )
    with tenant_session(t) as s:
        r = vencer_excepciones_y_constancias(s, t, ahora)
        assert (r["excepciones_vencidas"], r["constancias_vencidas"], r["hoy"]) == (1, 1, hoy.isoformat())
    with tenant_session(t) as s:
        estados = sorted(f[0] for f in s.execute(text("SELECT estado FROM modulo1.excepcion")))
        assert estados == ["otorgada", "revocada", "vencida"]  # la de vigencia == hoy sigue viva (inclusive)
        assert s.execute(text("SELECT estado FROM modulo1.constancia_cliente")).scalar() == "vencida"
        assert _contar_eventos(s, "ExcepcionVencida") == 1 and _contar_eventos(s, "ConstanciaVencida") == 1
        # HabilitacionRequiereRevaluacion lo decide la política de 7.2 (A-07): la excepción
        # vencida cita la decisión plantada → un aviso y un outbox; la constancia (sujeto p1)
        # no marca nada porque la decisión plantada no propone sujetos.
        assert s.execute(text("SELECT count(*) FROM modulo1.outbox_events")).scalar() == 1
        assert vencer_excepciones_y_constancias(s, t, ahora)["excepciones_vencidas"] == 0


class _StorageFalso:
    """Simula el bucket: `confirma` controla si el borrado físico se confirma; `presentes`
    dice qué claves existen (para la reconciliación de purgas cortadas)."""

    def __init__(self, confirma: bool, presentes: set[str] | None = None):
        self.confirma = confirma
        self.presentes = presentes if presentes is not None else None
        self.borradas: list[str] = []

    def borrar(self, clave: str) -> bool:
        self.borradas.append(clave)
        if self.confirma and self.presentes is not None:
            self.presentes.discard(clave)
        return self.confirma

    def existe(self, clave: str) -> bool:
        return True if self.presentes is None else clave in self.presentes

    def clave_para(self, *a): ...
    def url_prefirmada_put(self, *a): ...
    def url_prefirmada_get(self, *a): ...
    def inspeccionar(self, clave): ...


def _preparar_retencion(s, t):
    req = _definicion(s, t, retencion="30 days")
    hace_60 = ahora_utc() - timedelta(days=60)
    hoy = ahora_utc().date()
    viejo = _documento(s, t, req, hoy, estado_version="sucedida", clave=f"{t}/{{doc}}/viejo.pdf", creado_en=hace_60)
    _documento(s, t, req, hoy, estado_version="vigente", clave=f"{t}/{{doc}}/vigente.pdf", creado_en=hace_60)  # vigente: no
    _documento(s, t, req, hoy, estado_version="rechazada", clave=f"{t}/{{doc}}/reciente.pdf")  # dentro del plazo: no
    return viejo


def _estado_archivo(t, doc) -> tuple[str, str | None]:
    with tenant_session(t) as s:
        return s.execute(text("SELECT archivo_estado, clave_storage FROM modulo1.documento WHERE documento_id = :d"),
                         {"d": doc}).one()


def test_control_retencion_no_purga_si_borrado_no_confirmado(tenant_de_prueba):
    """A-05: si el bucket no confirma, la base queda en `purga_pendiente` (nunca `purgado`
    ni `confirmado` con archivo dudoso) y se reintenta en la vuelta siguiente."""
    t = tenant_de_prueba.tenant_id
    with tenant_session(t) as s:
        viejo = _preparar_retencion(s, t)
    clave = f"{t}/{viejo}/viejo.pdf"
    storage = _StorageFalso(confirma=False, presentes={clave})
    r = control_retencion(t, storage, ahora_utc())
    assert (r["marcados"], r["purgados"], r["no_confirmados"]) == (1, 0, 1)
    assert storage.borradas == [clave]
    assert _estado_archivo(t, viejo) == ("purga_pendiente", clave)
    with tenant_session(t) as s:
        assert _contar_eventos(s, "ArchivoPurgado") == 0
    # segunda vuelta: sigue pendiente (no se re-marca, se reintenta el borrado)
    r2 = control_retencion(t, storage, ahora_utc())
    assert (r2["marcados"], r2["purgados"], r2["no_confirmados"]) == (0, 0, 1)
    assert storage.borradas == [clave, clave]


def test_control_retencion_purga_si_borrado_confirmado(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    with tenant_session(t) as s:
        viejo = _preparar_retencion(s, t)
    storage = _StorageFalso(confirma=True)
    r = control_retencion(t, storage, ahora_utc())
    assert r["purgados"] == 1 and r["marcados"] == 1
    assert _estado_archivo(t, viejo) == ("purgado", None)
    with tenant_session(t) as s:
        assert _contar_eventos(s, "ArchivoPurgado") == 1
        assert s.execute(text("SELECT count(*) FROM modulo1.documento WHERE clave_storage IS NOT NULL")).scalar() == 2
    assert control_retencion(t, storage, ahora_utc())["candidatos"] == 0


def test_control_retencion_corte_entre_borrado_y_confirmacion_se_reconcilia(tenant_de_prueba):
    """A-05: la fase 1 commiteó `purga_pendiente`, el archivo se borró, y el proceso murió
    antes de confirmar en la base. La vuelta siguiente detecta que el archivo ya no existe
    y cierra la fase 2 sin volver a borrar nada ni perder el evento."""
    t = tenant_de_prueba.tenant_id
    with tenant_session(t) as s:
        viejo = _preparar_retencion(s, t)
    clave = f"{t}/{viejo}/viejo.pdf"

    class _MuereDespuesDeBorrar(_StorageFalso):
        def borrar(self, clave):
            self.presentes.discard(clave)
            raise RuntimeError("proceso caído después del unlink")

    caido = _MuereDespuesDeBorrar(confirma=True, presentes={clave})
    r = control_retencion(t, caido, ahora_utc())
    # el borrar "explotó" pero el archivo ya no existe → la reconciliación cierra igual
    assert r["purgados"] == 1
    assert _estado_archivo(t, viejo) == ("purgado", None)
    with tenant_session(t) as s:
        assert _contar_eventos(s, "ArchivoPurgado") == 1


def test_control_retencion_nunca_borra_dentro_de_la_transaccion(tenant_de_prueba, monkeypatch):
    """La fase 1 tiene que estar commiteada ANTES del primer borrado físico: si el proceso
    muere en el unlink, la base ya dice `purga_pendiente`."""
    t = tenant_de_prueba.tenant_id
    with tenant_session(t) as s:
        viejo = _preparar_retencion(s, t)
    vistos: list[tuple[str, str | None]] = []

    class _EspiaEstado(_StorageFalso):
        def borrar(self, clave):
            vistos.append(_estado_archivo(t, viejo))  # lectura desde OTRA sesión: solo ve lo commiteado
            return super().borrar(clave)

    control_retencion(t, _EspiaEstado(confirma=True), ahora_utc())
    assert vistos == [("purga_pendiente", f"{t}/{viejo}/viejo.pdf")]


# --- sistema ----------------------------------------------------------------------
def test_listar_tenants_devuelve_el_tenant_de_prueba(tenant_de_prueba):
    assert tenant_de_prueba.tenant_id in worker_main.listar_tenants()
    with platform_session() as s:
        ids = [str(f[0]) for f in s.execute(text("SELECT * FROM modulo1.listar_tenants()"))]
    assert tenant_de_prueba.tenant_id in ids


def test_correr_una_vuelta_procesa_colas_outbox_y_reloj(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    pub = PublicadorEnMemoria()
    with tenant_session(t) as s:
        encolar_outbox(s, t, "CumplimientoEmpresaAfectado", {"empresa": "x"})
        encolar(s, "evidencia_qr", {"stub": True}, tenant_id=t)
        encolar(s, "notificaciones", {"hola": True}, tenant_id=t)
    resumen = worker_main.correr_una_vuelta(_StorageFalso(confirma=True), pub)
    assert resumen["tenants"] >= 1 and resumen["outbox_publicados"] >= 1 and resumen["jobs"] >= 2
    assert any(e[0] == "CumplimientoEmpresaAfectado" for e in pub.eventos)
    with tenant_session(t) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.job_queue WHERE estado = 'completado'")).scalar() == 2
        nombres = {f[0] for f in s.execute(text("SELECT nombre FROM modulo1.latido_proceso WHERE tenant_id = :t AND ultimo_ok IS NOT NULL"), {"t": t})}
        assert {"drenaje_outbox", "control_vencimientos", "vencer_excepciones_y_constancias", "control_retencion"} <= nombres
    with platform_session() as s:
        assert s.execute(text("SELECT ultimo_ok FROM modulo1.latido_proceso WHERE nombre = 'worker' AND tenant_id IS NULL")).scalar() is not None


def test_vuelta_registra_latido_de_error_sin_frenar(tenant_de_prueba, monkeypatch):
    t = tenant_de_prueba.tenant_id

    def explota(session, tenant_id, ahora):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_main, "control_vencimientos", explota)
    worker_main.correr_una_vuelta(_StorageFalso(confirma=True), PublicadorEnMemoria())
    with tenant_session(t) as s:
        fila = s.execute(text("SELECT ultimo_error, detalle FROM modulo1.latido_proceso WHERE nombre = 'control_vencimientos' AND tenant_id = :t"), {"t": t}).first()
        assert fila is not None and fila[0] is not None and "boom" in fila[1]["error"]
        assert s.execute(text("SELECT ultimo_ok FROM modulo1.latido_proceso WHERE nombre = 'control_retencion' AND tenant_id = :t"), {"t": t}).scalar() is not None
