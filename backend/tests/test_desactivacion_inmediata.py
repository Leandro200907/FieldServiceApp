"""Un usuario desactivado no puede seguir usando un access token ya emitido: cada request
protegido comprueba el estado actual del usuario en la base (sin memoria local, efectivo
en todas las instancias). Salud sigue pública."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import tenant_session
from scripts import administracion as cli
from tests.conftest import limpiar_tenant


def test_desactivacion_invalida_el_access_token_de_inmediato(cliente_api, monkeypatch, capsys):
    slug = f"des-{uuid.uuid4().hex[:8]}"
    # 1) usuario activo
    assert cli.main(["crear-tenant", "--slug", slug, "--nombre", "Des"]) == 0
    tenant_id = capsys.readouterr().out.strip()
    try:
        monkeypatch.setenv("USUARIO_PASSWORD", "clave-segura-1")
        assert cli.main(["crear-usuario", "--tenant-slug", slug, "--email", "u@des.test", "--nombre", "U", "--rol", "responsable_legajos"]) == 0
        capsys.readouterr()
        # 2) login
        r = cliente_api.post("/v1/auth/login", json={"tenant_slug": slug, "email": "u@des.test", "password": "clave-segura-1"})
        assert r.status_code == 200
        access, refresh = r.json()["access_token"], r.json()["refresh_token"]
        h = {"Authorization": f"Bearer {access}"}
        # 3) ruta protegida → 200
        assert cliente_api.get("/v1/auth/yo", headers=h).status_code == 200
        assert cliente_api.get("/v1/consultas/propuestas_pendientes", headers=h).status_code == 200
        # 4) desactivar por CLI (otro "proceso": sólo la base cambia)
        assert cli.main(["desactivar-usuario", "--tenant-slug", slug, "--email", "u@des.test"]) == 0
        capsys.readouterr()
        # 5) mismo access token → 401 genérico
        r = cliente_api.get("/v1/auth/yo", headers=h)
        assert r.status_code == 401 and r.json()["error"] == {**r.json()["error"], "codigo": "no_autenticado", "mensaje": "No autenticado"}
        assert cliente_api.get("/v1/consultas/propuestas_pendientes", headers=h).status_code == 401
        assert cliente_api.post("/v1/comandos/alta_de_sujeto", json={"tipo_sujeto": "persona", "identificador_natural": "x"}, headers=h).status_code == 401
        # 6) refresh → 401; 7) login → 401
        assert cliente_api.post("/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401
        assert cliente_api.post("/v1/auth/login", json={"tenant_slug": slug, "email": "u@des.test", "password": "clave-segura-1"}).status_code == 401
        # 8) salud sigue pública
        assert cliente_api.get("/v1/salud/vivo").status_code == 200
        assert cliente_api.get("/v1/salud/listo").status_code in (200, 503)
    finally:
        limpiar_tenant(tenant_id)
        with tenant_session(tenant_id) as s:
            s.execute(text("DELETE FROM modulo1.usuario WHERE tenant_id = :t"), {"t": tenant_id})


def test_usuario_inexistente_e_inactivo_dan_el_mismo_401(cliente_api, tenant_de_prueba):
    """Token válido de un usuario que ya no existe vs. uno inactivo: respuesta idéntica."""
    t = tenant_de_prueba
    h_inactivo = t.headers("supervisor")
    h_borrado = t.headers("tecnico")
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.usuario SET activo = false WHERE usuario_id = :u"), {"u": t.usuarios["supervisor"]})
        s.execute(text("DELETE FROM modulo1.usuario WHERE usuario_id = :u"), {"u": t.usuarios["tecnico"]})
    a = cliente_api.get("/v1/auth/yo", headers=h_inactivo)
    b = cliente_api.get("/v1/auth/yo", headers=h_borrado)
    assert a.status_code == b.status_code == 401
    assert {k: v for k, v in a.json()["error"].items() if k != "request_id"} == {k: v for k, v in b.json()["error"].items() if k != "request_id"}
    # los demás usuarios del tenant siguen operando
    assert cliente_api.get("/v1/auth/yo", headers=t.headers("responsable_legajos")).status_code == 200
