"""Administración inicial por CLI (`scripts/administracion.py`): procedimiento completo
tenant → primer responsable → supervisor → desactivación, con contraseña por variable de
entorno o prompt seguro (nunca argv/stdout)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db import tenant_session
from scripts import administracion as cli
from tests.conftest import limpiar_tenant


@pytest.fixture
def slug():
    return f"cli-{uuid.uuid4().hex[:8]}"


def _login(cliente_api, slug, email, password):
    return cliente_api.post("/v1/auth/login", json={"tenant_slug": slug, "email": email, "password": password})


def test_procedimiento_completo(cliente_api, slug, monkeypatch, capsys):
    # 1) tenant
    assert cli.main(["crear-tenant", "--slug", slug, "--nombre", "ACME", "--zona-horaria", "UTC"]) == 0
    tenant_id = capsys.readouterr().out.strip()
    uuid.UUID(tenant_id)
    try:
        # 2) primer responsable + configuración; 3) supervisor — contraseña por variable, nunca en stdout
        monkeypatch.setenv("USUARIO_PASSWORD", "clave-de-ana-ñ")
        assert cli.main(["crear-usuario", "--tenant-slug", slug, "--email", "ana@acme.test", "--nombre", "Ana",
                         "--rol", "responsable_legajos", "--rol", "configuracion"]) == 0
        monkeypatch.setenv("USUARIO_PASSWORD", "clave-de-sup")
        assert cli.main(["crear-usuario", "--tenant-slug", slug, "--email", "sup@acme.test", "--nombre", "Sup", "--rol", "supervisor"]) == 0
        salida = capsys.readouterr()
        assert "clave-de" not in salida.out + salida.err
        assert _login(cliente_api, slug, "ana@acme.test", "clave-de-ana-ñ").status_code == 200
        r = _login(cliente_api, slug, "sup@acme.test", "clave-de-sup")
        assert r.status_code == 200
        refresh = r.json()["refresh_token"]
        yo = cliente_api.get("/v1/auth/yo", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
        assert yo["roles"] == ["supervisor"] and yo["tenant_id"] == tenant_id

        # tecnico exige sujeto_id → falla sin crear
        with pytest.raises(SystemExit):
            cli.main(["crear-usuario", "--tenant-slug", slug, "--email", "t@acme.test", "--nombre", "T", "--rol", "tecnico"])

        # 4) desactivar: login y refresh bloqueados, refresh tokens revocados; idempotente
        assert cli.main(["desactivar-usuario", "--tenant-slug", slug, "--email", "sup@acme.test"]) == 0
        assert "refresh tokens revocados: 1" in capsys.readouterr().out
        assert _login(cliente_api, slug, "sup@acme.test", "clave-de-sup").status_code == 401
        assert cliente_api.post("/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401
        assert cli.main(["desactivar-usuario", "--tenant-slug", slug, "--email", "sup@acme.test"]) == 0
        assert _login(cliente_api, slug, "ana@acme.test", "clave-de-ana-ñ").status_code == 200   # la otra sigue

        assert cli.main(["listar-usuarios", "--tenant-slug", slug]) == 0
        listado = capsys.readouterr().out
        assert "sup@acme.test  supervisor  INACTIVO" in listado and "ana@acme.test" in listado and "clave" not in listado

        # tenant inexistente / usuario inexistente: salida 2 con mensaje, sin traza
        with pytest.raises(SystemExit) as info:
            cli.main(["desactivar-usuario", "--tenant-slug", "no-existe", "--email", "x@x"])
        assert info.value.code == 2
    finally:
        limpiar_tenant(tenant_id)
        with tenant_session(tenant_id) as s:
            s.execute(text("DELETE FROM modulo1.usuario WHERE tenant_id = :t"), {"t": tenant_id})


def test_password_por_prompt_seguro_y_sin_terminal(monkeypatch):
    monkeypatch.delenv("USUARIO_PASSWORD", raising=False)
    # sin terminal interactiva: no se puede pedir → error 2, sin caer en argv
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit) as info:
        cli.obtener_password()
    assert info.value.code == 2
    # con terminal: getpass dos veces, sin eco (getpass no imprime lo tipeado)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    respuestas = iter(["secreta-1", "secreta-1"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(respuestas))
    assert cli.obtener_password() == "secreta-1"
    respuestas = iter(["a", "b"])
    with pytest.raises(SystemExit):
        cli.obtener_password()
    # más de 72 bytes por prompt: se rechaza antes de tocar la base
    respuestas = iter(["ñ" * 37, "ñ" * 37])
    with pytest.raises(cli.PasswordDemasiadoLarga):
        cli.obtener_password()


def test_la_contrasena_no_se_acepta_por_argv():
    with pytest.raises(SystemExit):
        cli.main(["crear-usuario", "--tenant-slug", "x", "--email", "e", "--nombre", "n", "--rol", "supervisor", "--password", "p"])


def test_listar_y_reprocesar_outbox_estancado(tenant_de_prueba, capsys):
    """Reauditoría Fase 2 punto 5: un evento que agota los reintentos queda estancado,
    visible por CLI, y se reactiva a mano — nunca desaparece solo."""
    from datetime import timedelta

    from app.comun.eventos import encolar_outbox
    from app.comun.reloj import ahora_utc
    from app.worker.outbox import MAX_INTENTOS_OUTBOX, PublicadorEnMemoria, drenar_outbox

    t = tenant_de_prueba
    ahora = ahora_utc()
    with tenant_session(t.tenant_id) as s:
        encolar_outbox(s, t.tenant_id, "CumplimientoEmpresaAfectado", {"empresa": "x"}, disponible_en=ahora)
    pub = PublicadorEnMemoria(fallar_con=RuntimeError("módulo 2 caído"))
    for _ in range(MAX_INTENTOS_OUTBOX):
        with tenant_session(t.tenant_id) as s:
            drenar_outbox(s, t.tenant_id, pub, ahora=ahora)
        ahora += timedelta(hours=6)

    assert cli.main(["listar-outbox-estancado", "--tenant-slug", t.slug]) == 0
    salida = capsys.readouterr().out
    assert "CumplimientoEmpresaAfectado" in salida and "módulo 2 caído" in salida

    assert cli.main(["reprocesar-outbox", "--tenant-slug", t.slug]) == 0
    assert capsys.readouterr().out.strip() == "reactivados: 1"

    assert cli.main(["listar-outbox-estancado", "--tenant-slug", t.slug]) == 0
    assert capsys.readouterr().out.strip() == ""
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT estancado_en, intentos FROM modulo1.outbox_events")).one() == (None, 0)
