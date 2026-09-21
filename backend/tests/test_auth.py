"""Auth (9.2) contra base real: login, refresh con rotación, logout, /yo y rechazo de tokens.

El conftest carga un `password_hash` fijo para 'secreto' que puede no ser un bcrypt válido,
así que cada test que hace login primero pisa el hash del usuario con `hashear_password`.
"""
from __future__ import annotations

from sqlalchemy import text

from app.auth.jwt import hash_de_token
from app.auth.passwords import hashear_password, verificar_password
from app.db import tenant_session
from tests.conftest import token_para

PASSWORD = "secreto"


def _fijar_password(tenant, rol: str, password: str = PASSWORD) -> None:
    with tenant_session(tenant.tenant_id) as s:
        s.execute(
            text("UPDATE modulo1.usuario SET password_hash = :h WHERE usuario_id = :u"),
            {"h": hashear_password(password), "u": tenant.usuarios[rol]},
        )


def _login(cliente, tenant, rol: str, password: str = PASSWORD):
    return cliente.post(
        "/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": f"{rol}@{tenant.slug}.test", "password": password},
    )


def _estado_refresh(tenant, refresh_token: str):
    with tenant_session(tenant.tenant_id) as s:
        return s.execute(
            text("SELECT revocado_en FROM modulo1.refresh_token WHERE token_hash = :h"),
            {"h": hash_de_token(refresh_token)},
        ).first()


# --------------------------------------------------------------------------- passwords


def test_hash_y_verificacion_de_password():
    h = hashear_password("clave-123")
    assert h.startswith("$2b$")
    assert verificar_password("clave-123", h)
    assert not verificar_password("clave-124", h)
    assert not verificar_password("clave-123", "no-es-un-hash")
    assert not verificar_password("clave-123", None)


# --------------------------------------------------------------------------- login


def test_login_ok_devuelve_par_de_tokens(cliente_api, tenant_de_prueba):
    _fijar_password(tenant_de_prueba, "responsable_legajos")
    r = _login(cliente_api, tenant_de_prueba, "responsable_legajos")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["expires_in"] > 0
    assert cuerpo["access_token"] and cuerpo["refresh_token"]

    # El access token sirve para /yo y trae exactamente lo del usuario.
    yo = cliente_api.get("/v1/auth/yo", headers={"Authorization": f"Bearer {cuerpo['access_token']}"})
    assert yo.status_code == 200
    assert yo.json() == {
        "tenant_id": tenant_de_prueba.tenant_id,
        "usuario_id": tenant_de_prueba.usuarios["responsable_legajos"],
        "roles": ["responsable_legajos"],
        "sujeto_id": None,
    }
    # El refresh quedó persistido como hash, vigente.
    fila = _estado_refresh(tenant_de_prueba, cuerpo["refresh_token"])
    assert fila is not None and fila[0] is None


def test_login_tecnico_trae_sujeto_id(cliente_api, tenant_de_prueba):
    _fijar_password(tenant_de_prueba, "tecnico")
    r = _login(cliente_api, tenant_de_prueba, "tecnico")
    assert r.status_code == 200, r.text
    yo = cliente_api.get("/v1/auth/yo", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert yo.json()["sujeto_id"] == tenant_de_prueba.sujeto_tecnico
    assert yo.json()["roles"] == ["tecnico"]


def test_login_password_mala(cliente_api, tenant_de_prueba):
    _fijar_password(tenant_de_prueba, "supervisor")
    r = _login(cliente_api, tenant_de_prueba, "supervisor", password="otra")
    assert r.status_code == 401
    assert r.json()["error"]["codigo"] == "no_autenticado"


def test_login_email_inexistente_misma_respuesta(cliente_api, tenant_de_prueba):
    r = cliente_api.post(
        "/v1/auth/login",
        json={"tenant_slug": tenant_de_prueba.slug, "email": "nadie@nada.test", "password": PASSWORD},
    )
    assert r.status_code == 401
    assert r.json()["error"]["codigo"] == "no_autenticado"


def test_login_tenant_slug_inexistente(cliente_api, tenant_de_prueba):
    _fijar_password(tenant_de_prueba, "supervisor")
    r = cliente_api.post(
        "/v1/auth/login",
        json={"tenant_slug": "no-existe", "email": f"supervisor@{tenant_de_prueba.slug}.test", "password": PASSWORD},
    )
    assert r.status_code == 401
    assert r.json()["error"]["codigo"] == "no_autenticado"


def test_login_usuario_inactivo(cliente_api, tenant_de_prueba):
    _fijar_password(tenant_de_prueba, "configuracion")
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        s.execute(
            text("UPDATE modulo1.usuario SET activo = false WHERE usuario_id = :u"),
            {"u": tenant_de_prueba.usuarios["configuracion"]},
        )
    r = _login(cliente_api, tenant_de_prueba, "configuracion")
    assert r.status_code == 401


# --------------------------------------------------------------------------- refresh


def test_refresh_rota_y_el_viejo_deja_de_servir(cliente_api, tenant_de_prueba):
    _fijar_password(tenant_de_prueba, "supervisor")
    viejo = _login(cliente_api, tenant_de_prueba, "supervisor").json()["refresh_token"]

    r = cliente_api.post("/v1/auth/refresh", json={"refresh_token": viejo})
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert nuevo["refresh_token"] != viejo
    assert nuevo["access_token"]

    # El viejo quedó revocado en la tabla y ya no rota.
    assert _estado_refresh(tenant_de_prueba, viejo)[0] is not None
    r2 = cliente_api.post("/v1/auth/refresh", json={"refresh_token": viejo})
    assert r2.status_code == 401
    assert r2.json()["error"]["codigo"] == "no_autenticado"

    # El nuevo sí sirve, y el access nuevo autentica.
    r3 = cliente_api.post("/v1/auth/refresh", json={"refresh_token": nuevo["refresh_token"]})
    assert r3.status_code == 200
    yo = cliente_api.get("/v1/auth/yo", headers={"Authorization": f"Bearer {nuevo['access_token']}"})
    assert yo.status_code == 200 and yo.json()["roles"] == ["supervisor"]


def test_refresh_rechaza_access_token(cliente_api, tenant_de_prueba):
    _fijar_password(tenant_de_prueba, "supervisor")
    access = _login(cliente_api, tenant_de_prueba, "supervisor").json()["access_token"]
    r = cliente_api.post("/v1/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


def test_refresh_token_basura(cliente_api):
    r = cliente_api.post("/v1/auth/refresh", json={"refresh_token": "no.es.jwt"})
    assert r.status_code == 401
    assert r.json()["error"]["codigo"] == "no_autenticado"


# --------------------------------------------------------------------------- logout


def test_logout_revoca_refresh(cliente_api, tenant_de_prueba):
    _fijar_password(tenant_de_prueba, "tecnico")
    par = _login(cliente_api, tenant_de_prueba, "tecnico").json()
    cabeceras = {"Authorization": f"Bearer {par['access_token']}"}

    r = cliente_api.post("/v1/auth/logout", json={"refresh_token": par["refresh_token"]}, headers=cabeceras)
    assert r.status_code == 200 and r.json() == {"revocado": True}
    assert _estado_refresh(tenant_de_prueba, par["refresh_token"])[0] is not None

    # Ya no rota, y un segundo logout es inofensivo.
    assert cliente_api.post("/v1/auth/refresh", json={"refresh_token": par["refresh_token"]}).status_code == 401
    r2 = cliente_api.post("/v1/auth/logout", json={"refresh_token": par["refresh_token"]}, headers=cabeceras)
    assert r2.status_code == 200 and r2.json() == {"revocado": False}


def test_logout_requiere_autenticacion(cliente_api):
    r = cliente_api.post("/v1/auth/logout", json={"refresh_token": "x"})
    assert r.status_code == 401


# --------------------------------------------------------------------------- /yo y rechazo de tokens


def test_yo_con_token_del_conftest(cliente_api, tenant_de_prueba):
    r = cliente_api.get("/v1/auth/yo", headers=tenant_de_prueba.headers("supervisor"))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "tenant_id": tenant_de_prueba.tenant_id,
        "usuario_id": tenant_de_prueba.usuarios["supervisor"],
        "roles": ["supervisor"],
        "sujeto_id": None,
    }


def test_yo_sin_authorization(cliente_api):
    r = cliente_api.get("/v1/auth/yo")
    assert r.status_code == 401
    assert r.json()["error"]["codigo"] == "no_autenticado"


def test_yo_token_vencido(cliente_api, tenant_de_prueba):
    vencido = token_para(tenant_de_prueba.tenant_id, tenant_de_prueba.usuarios["supervisor"], ["supervisor"], minutos=-1)
    r = cliente_api.get("/v1/auth/yo", headers={"Authorization": f"Bearer {vencido}"})
    assert r.status_code == 401
    cuerpo = r.json()
    assert set(cuerpo) == {"error"}
    assert cuerpo["error"]["codigo"] == "no_autenticado"
    assert set(cuerpo["error"]) == {"codigo", "mensaje", "detalles", "request_id"}


def test_yo_token_firmado_con_otro_secreto(cliente_api, tenant_de_prueba):
    import jwt as pyjwt

    from datetime import datetime, timedelta, timezone

    ahora = datetime.now(timezone.utc)
    falso = pyjwt.encode(
        {
            "sub": tenant_de_prueba.usuarios["supervisor"],
            "tenant_id": tenant_de_prueba.tenant_id,
            "roles": ["supervisor"],
            "sujeto_id": None,
            "iat": ahora,
            "exp": ahora + timedelta(minutes=5),
            "tipo": "access",
        },
        "otro-secreto",
        algorithm="HS256",
    )
    r = cliente_api.get("/v1/auth/yo", headers={"Authorization": f"Bearer {falso}"})
    assert r.status_code == 401


def test_yo_rechaza_esquema_no_bearer(cliente_api, tenant_de_prueba):
    r = cliente_api.get("/v1/auth/yo", headers={"Authorization": f"Basic {tenant_de_prueba.token('supervisor')}"})
    assert r.status_code == 401
