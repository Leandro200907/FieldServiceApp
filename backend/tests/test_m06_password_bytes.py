"""M-06: el límite de contraseña se mide en BYTES UTF-8 (72, límite de bcrypt), nunca se
trunca, y el rechazo es un 422 estable que no registra ni devuelve la contraseña.

Superficies revisadas: login (`/v1/auth/login`), creación (`scripts/administracion.py` →
`hashear_password`); v1 no tiene endpoints de cambio ni restablecimiento de contraseña
(toda alta pasa por `hashear_password`, la única puerta de hasheo)."""
from __future__ import annotations

import logging

import pytest
from sqlalchemy import text

from app.auth.passwords import MAX_BYTES, PasswordDemasiadoLarga, bytes_de, hashear_password, verificar_password
from app.db import tenant_session

LIMITE_ASCII = "a" * 72                            # 72 caracteres, 72 bytes
LIMITE_MULTIBYTE = "ñ" * 36                        # 36 caracteres, 72 bytes
UN_BYTE_DE_MAS_ASCII = "a" * 73                    # 73 bytes
UN_BYTE_DE_MAS_MULTIBYTE = "ñ" * 35 + "abc"        # 70 + 3 = 73 bytes, 38 caracteres
CARACTERES_72_BYTES_144 = "😀" * 36                 # 36 caracteres, 144 bytes: pasa por caracteres, no por bytes

assert bytes_de(LIMITE_ASCII) == 72 and bytes_de(LIMITE_MULTIBYTE) == 72
assert bytes_de(UN_BYTE_DE_MAS_ASCII) == 73 and bytes_de(UN_BYTE_DE_MAS_MULTIBYTE) == 73


# --------------------------------------------------------------------------- hasheo / verificación


@pytest.mark.parametrize("password", [LIMITE_ASCII, LIMITE_MULTIBYTE, "é" * 35 + "ab"])
def test_exactamente_en_el_limite_se_acepta(password):
    assert bytes_de(password) == MAX_BYTES
    h = hashear_password(password)
    assert verificar_password(password, h)


@pytest.mark.parametrize("password", [UN_BYTE_DE_MAS_ASCII, UN_BYTE_DE_MAS_MULTIBYTE, "ñ" * 37, CARACTERES_72_BYTES_144])
def test_un_byte_o_mas_por_encima_no_se_hashea_ni_se_trunca(password):
    assert bytes_de(password) > MAX_BYTES
    with pytest.raises(PasswordDemasiadoLarga) as info:
        hashear_password(password)
    assert password not in str(info.value)
    assert info.value.bytes_recibidos == bytes_de(password)


def test_dos_contrasenas_con_los_primeros_72_bytes_iguales_no_son_equivalentes():
    """bcrypt truncaría a 72 bytes: `LIMITE + 'x'` verificaría contra el hash de `LIMITE`.
    Acá la más larga nunca llega a bcrypt: no verifica y no se hashea."""
    h = hashear_password(LIMITE_ASCII)
    assert verificar_password(LIMITE_ASCII, h)
    assert not verificar_password(LIMITE_ASCII + "x", h)
    assert not verificar_password(LIMITE_ASCII + "ñ", h)
    h2 = hashear_password(LIMITE_MULTIBYTE)
    assert verificar_password(LIMITE_MULTIBYTE, h2)
    assert not verificar_password(LIMITE_MULTIBYTE + "a", h2)
    assert not verificar_password("ñ" * 37, h2)


def test_verificar_con_hash_vacio_o_roto_es_falso_sin_excepcion():
    assert verificar_password("x", None) is False
    assert verificar_password("x", "") is False
    assert verificar_password("x", "no-es-un-hash") is False


# --------------------------------------------------------------------------- login por HTTP


def _login(cliente_api, t, password):
    return cliente_api.post("/v1/auth/login", json={"tenant_slug": t.slug, "email": f"supervisor@{t.slug}.test", "password": password})


def test_login_en_el_limite_funciona_y_un_byte_mas_es_422_estable(cliente_api, tenant_de_prueba, caplog):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.usuario SET password_hash = :h WHERE usuario_id = :u"),
                  {"h": hashear_password(LIMITE_MULTIBYTE), "u": t.usuarios["supervisor"]})
    assert _login(cliente_api, t, LIMITE_MULTIBYTE).status_code == 200
    # El prefijo con un byte más NO entra (ni por truncamiento ni por validación laxa).
    with caplog.at_level(logging.DEBUG):
        r = _login(cliente_api, t, LIMITE_MULTIBYTE + "a")
    assert r.status_code == 422, r.text
    cuerpo = r.json()["error"]
    assert cuerpo["codigo"] == "validacion" and cuerpo["request_id"]
    assert cuerpo["detalles"][0]["loc"] == ["body", "password"] and "bytes" in cuerpo["detalles"][0]["mensaje"]
    assert "ñññ" not in r.text                   # no devuelve la contraseña
    assert "ñññ" not in caplog.text              # ni la registra
    # 72 caracteres multibyte (144 bytes): rechazado por bytes aunque pase por caracteres.
    assert _login(cliente_api, t, CARACTERES_72_BYTES_144).status_code == 422
    assert _login(cliente_api, t, UN_BYTE_DE_MAS_ASCII).status_code == 422
    # Contraseña incorrecta dentro del límite: 401 genérico, no 422.
    assert _login(cliente_api, t, LIMITE_ASCII).status_code == 401


def test_el_422_de_validacion_nunca_devuelve_el_input(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    r = cliente_api.post("/v1/auth/login", json={"tenant_slug": t.slug, "email": "", "password": "SECRETO-visible?"})
    assert r.status_code == 422
    assert "SECRETO" not in r.text
    assert all(set(d) == {"loc", "tipo", "mensaje"} for d in r.json()["error"]["detalles"])


# --------------------------------------------------------------------------- creación (CLI)


def test_cli_crear_usuario_rechaza_73_bytes_sin_imprimir_la_contrasena(tenant_de_prueba, monkeypatch, capsys):
    from scripts import administracion as cli
    t = tenant_de_prueba
    monkeypatch.setenv("USUARIO_PASSWORD", UN_BYTE_DE_MAS_ASCII)
    rc = cli.main(["crear-usuario", "--tenant-slug", t.slug, "--email", "nuevo@x.test", "--nombre", "N", "--rol", "supervisor"])
    salida = capsys.readouterr()
    assert rc == 2 and "password_demasiado_larga" in salida.err and UN_BYTE_DE_MAS_ASCII not in salida.err + salida.out
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.usuario WHERE email = 'nuevo@x.test'")).scalar() == 0

    monkeypatch.setenv("USUARIO_PASSWORD", LIMITE_MULTIBYTE)
    rc = cli.main(["crear-usuario", "--tenant-slug", t.slug, "--email", "nuevo@x.test", "--nombre", "N", "--rol", "supervisor"])
    salida = capsys.readouterr()
    assert rc == 0 and LIMITE_MULTIBYTE not in salida.out
    with tenant_session(t.tenant_id) as s:
        h = s.execute(text("SELECT password_hash FROM modulo1.usuario WHERE email = 'nuevo@x.test'")).scalar()
    assert verificar_password(LIMITE_MULTIBYTE, h) and not verificar_password(LIMITE_MULTIBYTE + "a", h)
