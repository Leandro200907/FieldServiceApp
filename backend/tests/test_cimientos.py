"""Sanity de los cimientos compartidos: app levanta, fixture de tenant funciona, RLS aísla."""
from sqlalchemy import text

from app.db import tenant_session


def test_salud(cliente_api):
    r = cliente_api.get("/v1/salud/vivo")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_error_envelope_en_404(cliente_api):
    r = cliente_api.get("/v1/no-existe")
    assert r.status_code == 404


def test_tenant_de_prueba_aislado(tenant_de_prueba):
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.usuario")).scalar() == 4
        assert s.execute(text("SELECT count(*) FROM modulo1.tenant")).scalar() == 1
