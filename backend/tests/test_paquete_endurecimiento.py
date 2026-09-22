"""Reauditoría Fase 2 punto 3: PAQUETE_SECRET obligatorio en producción, proxy confiable
para el origen del rate limiter (nunca `X-Forwarded-For` a ciegas), y cota de memoria del
`RateLimiter` en proceso."""
from __future__ import annotations

import time

import pytest

from app.comun.red import origen_real
from app.modules.paquete.servicio import PaqueteSecretoFaltante, RateLimiter
from tests.test_h01_capacidades_v1 import _ok, _post

# --------------------------------------------------------------------------- origen_real / proxy confiable


def test_sin_proxies_confiables_x_forwarded_for_se_ignora_siempre():
    assert origen_real("203.0.113.9", "1.2.3.4", "") == "203.0.113.9"


def test_peer_no_confiable_x_forwarded_for_se_ignora():
    """Aunque haya proxies confiables configurados, si la conexión INMEDIATA no es uno de
    ellos, el header no vale nada — cualquiera podría haberlo mandado."""
    assert origen_real("198.51.100.1", "1.2.3.4", "10.0.0.0/8") == "198.51.100.1"


def test_peer_confiable_usa_el_primer_salto_del_header():
    assert origen_real("10.0.0.5", "203.0.113.9, 10.0.0.5", "10.0.0.0/8") == "203.0.113.9"
    assert origen_real("10.0.0.5", None, "10.0.0.0/8") == "10.0.0.5"  # confiable pero sin header: usa el peer


def test_ip_individual_y_entrada_invalida_en_la_lista():
    assert origen_real("10.0.0.5", "203.0.113.9", "no-es-una-ip, 10.0.0.5/32") == "203.0.113.9"


def test_sin_peer_ni_header_no_lanza():
    assert origen_real(None, None, "10.0.0.0/8") == "?"


def test_publico_paquete_ignora_x_forwarded_for_por_defecto(cliente_api, tenant_de_prueba):
    """Integración: sin PROXIES_CONFIABLES (default de este entorno de test), el rate
    limiter usa la IP real de la conexión de test, no lo que venga en el header."""
    from sqlalchemy import text
    from app.db import tenant_session
    from tests import apoyo

    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, "persona_proxy")
    r = _ok(_post(cliente_api, t, "responsable_legajos", "generar_paquete_entrega", {"sujeto_id": "persona_proxy"}))
    token = r["url"].rsplit("/", 1)[1]
    resp = cliente_api.get(f"/v1/publico/paquete/{token}", headers={"X-Forwarded-For": "9.9.9.9"})
    assert resp.status_code == 200  # no explota ni cambia de comportamiento por el header


# --------------------------------------------------------------------------- PAQUETE_SECRET obligatorio


def test_secreto_derivado_en_desarrollo_pero_obligatorio_en_produccion(monkeypatch):
    import app.modules.paquete.servicio as paq

    monkeypatch.delenv("PAQUETE_SECRET", raising=False)
    monkeypatch.setattr(paq.settings, "entorno", "desarrollo")
    assert paq._secreto() == f"paquete:{paq.settings.jwt_secret}".encode()

    monkeypatch.setattr(paq.settings, "entorno", "produccion")
    with pytest.raises(PaqueteSecretoFaltante):
        paq._secreto()

    monkeypatch.setenv("PAQUETE_SECRET", "un-secreto-propio-y-largo")
    assert paq._secreto() == b"un-secreto-propio-y-largo"


# --------------------------------------------------------------------------- cota de memoria del RateLimiter


def test_barrer_purga_solo_claves_sin_actividad_en_la_ventana():
    lim = RateLimiter(max_por_minuto=5)
    t = 1000.0
    for i in range(6):
        lim.permitir(f"clave-{i}", ahora=t)
    assert len(lim._golpes) == 6
    lim._barrer(t + 61)  # 61s después: ninguna de las 6 tiene actividad en los últimos 60s
    assert lim._golpes == {}


def test_barrer_no_toca_actividad_dentro_de_la_ventana():
    lim = RateLimiter(max_por_minuto=5)
    t = 1000.0
    lim.permitir("activa", ahora=t)
    lim._barrer(t + 2)  # 2s después: sigue dentro de los 60s
    assert "activa" in lim._golpes


def test_permitir_dispara_el_barrido_automatico_cada_n_llamadas():
    lim = RateLimiter(max_por_minuto=5, cada=3)
    t = 1000.0
    for i in range(3):
        lim.permitir(f"clave-{i}", ahora=t)
    assert lim._llamadas == 0  # el contador se resetea cuando el barrido se dispara


def test_rate_limiter_sigue_limitando_max_por_minuto():
    lim = RateLimiter(max_por_minuto=2)
    t = 2000.0
    assert lim.permitir("k", ahora=t) is True
    assert lim.permitir("k", ahora=t + 1) is True
    assert lim.permitir("k", ahora=t + 2) is False
