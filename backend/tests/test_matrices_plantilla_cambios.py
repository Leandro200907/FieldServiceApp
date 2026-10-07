"""Diferencias de plantilla en plantillas_globales y permisos de matriz al responsable."""
from __future__ import annotations

import uuid

from tests.test_h04_plantillas_globales import _copiar_matriz, _subir_version, catalogo  # noqa: F401 — fixture
from tests.test_h04_plantillas_globales import CMD

from tests import apoyo


def _cambios(cliente_api, t, catalogo):
    cons = cliente_api.get("/v1/consultas/plantillas_globales", headers=t.headers("responsable_legajos")).json()
    m = next(x for x in cons["matrices"] if x["matriz_global_id"] == catalogo["matriz"])
    return m["copias_locales"][0]["cambios"]


def test_cambios_plantilla_cuatro_tipos(cliente_api, catalogo, tenant_de_prueba):
    t = tenant_de_prueba
    suf = catalogo["sufijo"]
    r, body = _copiar_matriz(cliente_api, t, catalogo)
    assert r.status_code == 200
    assert _cambios(cliente_api, t, catalogo) == []

    altura_gid = catalogo["defs"][f"Altura {suf}"]
    apto_gid = catalogo["defs"][f"Apto {suf}"]
    mid = catalogo["matriz"]
    art_gid = catalogo["defs"][f"ART {suf}"]
    with apoyo.conexion_owner() as conn:
        conn.execute(
            "INSERT INTO plataforma.definicion_requisito_global (nombre, categoria, tipo_sujeto_aplicable, version, activa, descripcion) "
            "VALUES (%s, 'documento', 'vehiculo', 1, true, 'test') RETURNING definicion_global_id",
            (f"Vehiculo {suf}",),
        )
        nuevo_gid = str(conn.execute("SELECT definicion_global_id FROM plataforma.definicion_requisito_global WHERE nombre = %s", (f"Vehiculo {suf}",)).fetchone()[0])
        conn.execute(
            "INSERT INTO plataforma.linea_matriz_global (matriz_global_id, definicion_global_id, clasificacion, bloqueante_durante_ejecucion) "
            "VALUES (%s, %s, 'bloqueante_duro', true)",
            (mid, nuevo_gid),
        )
        conn.execute(
            "UPDATE plataforma.linea_matriz_global SET clasificacion = 'bloqueante_duro' WHERE matriz_global_id = %s AND definicion_global_id = %s",
            (mid, altura_gid),
        )
        conn.execute(
            "UPDATE plataforma.linea_matriz_global SET clasificacion = 'excepcionable', bloqueante_durante_ejecucion = false "
            "WHERE matriz_global_id = %s AND definicion_global_id = %s",
            (mid, art_gid),
        )
        conn.execute("DELETE FROM plataforma.linea_matriz_global WHERE matriz_global_id = %s AND definicion_global_id = %s", (mid, apto_gid))
        conn.execute("UPDATE plataforma.matriz_global SET version = 3 WHERE matriz_global_id = %s", (mid,))
        conn.commit()

    cambios = _cambios(cliente_api, t, catalogo)
    tipos = {c["tipo"] for c in cambios}
    assert tipos == {"agregado", "quitado", "pasa_a_bloquear", "deja_de_bloquear"}
    pasa = next(c for c in cambios if c["tipo"] == "pasa_a_bloquear")
    assert pasa["nombre"] == f"Altura {suf}" and pasa["grupo"] == "persona"
    quitado = next(c for c in cambios if c["tipo"] == "quitado")
    assert quitado["nombre"] == f"Apto {suf}"
    agregado = next(c for c in cambios if c["tipo"] == "agregado")
    assert agregado["nombre"] == f"Vehiculo {suf}" and agregado["grupo"] == "vehiculo"
    deja = next(c for c in cambios if c["tipo"] == "deja_de_bloquear")
    assert deja["nombre"] == f"ART {suf}"


def test_responsable_publica_matriz_supervisor_403(cliente_api, tenant_de_prueba):
    from tests.test_comandos_requisitos import _alta_def

    t = tenant_de_prueba
    rid = _alta_def(cliente_api, t, "Apto RL")
    body = {
        "cliente_id": str(uuid.uuid4()),
        "locacion_id": str(uuid.uuid4()),
        "tipo_servicio_id": str(uuid.uuid4()),
        "vigente_desde": "2026-06-01",
        "lineas": [{"requisito_definicion_id": rid, "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True}],
    }
    for rol in ("supervisor", "tecnico"):
        assert cliente_api.post(f"{CMD}/publicar_version_de_matriz", json=body, headers=t.headers(rol)).status_code == 403
    assert cliente_api.post(f"{CMD}/publicar_version_de_matriz", json=body, headers=t.headers("responsable_legajos")).status_code == 200
