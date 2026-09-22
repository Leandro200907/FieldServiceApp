"""Auditoría externa (ChatGPT + revisión propia): `identidad_actual` revalidaba `activo`
en cada request pero confiaba en `roles`/`sujeto_id` tal como venían en el JWT, sin
comparar contra la fila actual de `usuario`. Un cambio operativo de rol o de legajo (hoy
sólo posible escribiendo la base directo, no hay comando de CLI para editarlos) no tenía
efecto hasta que el access token expirara — mismo hueco que ya estaba documentado para la
reactivación, nunca extendido a roles."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import tenant_session
from scripts import administracion as cli


def test_cambio_de_rol_en_la_base_es_efectivo_en_el_siguiente_request(cliente_api, monkeypatch, capsys):
    slug = f"rol-{uuid.uuid4().hex[:8]}"
    assert cli.main(["crear-tenant", "--slug", slug, "--nombre", "Rol"]) == 0
    tenant_id = capsys.readouterr().out.strip()
    try:
        monkeypatch.setenv("USUARIO_PASSWORD", "clave-segura-1")
        assert cli.main(["crear-usuario", "--tenant-slug", slug, "--email", "u@rol.test", "--nombre", "U",
                         "--rol", "tecnico", "--sujeto-id", "persona_x"]) == 0
        capsys.readouterr()
        with tenant_session(tenant_id) as s:
            from tests import apoyo
            apoyo.legajo(s, tenant_id, "persona_x")

        r = cliente_api.post("/v1/auth/login", json={"tenant_slug": slug, "email": "u@rol.test", "password": "clave-segura-1"})
        assert r.status_code == 200
        access = r.json()["access_token"]
        h = {"Authorization": f"Bearer {access}"}

        # el token nace con rol técnico + sujeto_id propio
        yo = cliente_api.get("/v1/auth/yo", headers=h).json()
        assert yo["roles"] == ["tecnico"] and yo["sujeto_id"] == "persona_x"
        # con ese rol, mi_legajo funciona y bandeja_validacion_evidencia (responsable/configuracion) no
        assert cliente_api.get("/v1/consultas/mi_legajo", headers=h).status_code == 200
        assert cliente_api.get("/v1/consultas/bandeja_validacion_evidencia", headers=h).status_code == 403

        # cambio operativo directo en la base (no hay comando de CLI para esto): pasa a
        # responsable_legajos, sin legajo propio — simula una corrección administrativa real
        with tenant_session(tenant_id) as s:
            s.execute(text("UPDATE modulo1.usuario SET roles = ARRAY['responsable_legajos'], sujeto_id = NULL "
                           "WHERE tenant_id = :t AND email = 'u@rol.test'"), {"t": tenant_id})

        # el MISMO access token, sin volver a loguearse, tiene que reflejar el cambio YA
        yo2 = cliente_api.get("/v1/auth/yo", headers=h).json()
        assert yo2["roles"] == ["responsable_legajos"] and yo2["sujeto_id"] is None
        # ya no puede usar el permiso de técnico...
        assert cliente_api.get("/v1/consultas/mi_legajo", headers=h).status_code == 403
        # ...y ya tiene el de responsable_legajos
        assert cliente_api.get("/v1/consultas/bandeja_validacion_evidencia", headers=h).status_code == 200
    finally:
        with tenant_session(tenant_id) as s:
            for tabla in ("refresh_token", "legajo", "usuario", "tenant"):
                s.execute(text(f"DELETE FROM modulo1.{tabla} WHERE tenant_id = :t"), {"t": tenant_id})
