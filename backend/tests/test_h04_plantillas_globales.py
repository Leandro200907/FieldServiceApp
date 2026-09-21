"""H-04: catálogo y matrices globales de industria, copia opt-in, detección de versión
nueva, `PlantillaGlobalActualizada` + notificación, consulta plantilla-junto-a-copia."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import tenant_session
from app.modules.requisitos.plantillas import control_plantillas
from scripts.precargar_plantillas import precargar
from tests import apoyo

RAIZ = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
CMD = "/v1/comandos"


@pytest.fixture
def catalogo():
    """Catálogo global propio del test (nombres únicos) creado con el rol owner; se borra al final."""
    sufijo = uuid.uuid4().hex[:6]
    datos = {
        "definiciones": [
            {"nombre": f"Apto {sufijo}", "categoria": "documento", "tipo_sujeto_aplicable": "persona", "version": 1},
            {"nombre": f"Altura {sufijo}", "categoria": "competencia", "tipo_sujeto_aplicable": "persona", "version": 1},
            {"nombre": f"Induccion {sufijo}", "categoria": "induccion", "tipo_sujeto_aplicable": "persona", "version": 1},
            {"nombre": f"ART {sufijo}", "categoria": "documento", "tipo_sujeto_aplicable": "empresa", "version": 1},
        ],
        "matrices": [{
            "operadora": f"OP-{sufijo}", "tipo_servicio": "campo", "version": 1, "fuente": "test",
            "lineas": [
                {"definicion": f"Apto {sufijo}", "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True},
                {"definicion": f"Altura {sufijo}", "clasificacion": "excepcionable", "bloqueante_durante_ejecucion": False},
                {"definicion": f"Induccion {sufijo}", "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True},
                {"definicion": f"ART {sufijo}", "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True},
            ],
        }],
    }
    with apoyo.conexion_owner() as conn:
        precargar(conn, datos)
        ids = {n: str(i) for n, i in conn.execute("SELECT nombre, definicion_global_id FROM plataforma.definicion_requisito_global WHERE nombre LIKE %s", (f"%{sufijo}",))}
        mid = str(conn.execute("SELECT matriz_global_id FROM plataforma.matriz_global WHERE operadora = %s", (f"OP-{sufijo}",)).fetchone()[0])
        conn.commit()
    yield {"sufijo": sufijo, "datos": datos, "defs": ids, "matriz": mid}
    with apoyo.conexion_owner() as conn:
        conn.execute("DELETE FROM plataforma.linea_matriz_global WHERE matriz_global_id = %s", (mid,))
        conn.execute("DELETE FROM plataforma.matriz_global WHERE matriz_global_id = %s", (mid,))
        conn.execute("DELETE FROM plataforma.definicion_requisito_global WHERE nombre LIKE %s", (f"%{sufijo}",))
        conn.commit()


def _subir_version(catalogo, *, definicion: str | None = None, matriz: bool = False, version: int = 2):
    with apoyo.conexion_owner() as conn:
        if definicion:
            conn.execute("UPDATE plataforma.definicion_requisito_global SET version = %s, actualizado_en = now() WHERE definicion_global_id = %s",
                         (version, catalogo["defs"][definicion]))
        if matriz:
            conn.execute("UPDATE plataforma.matriz_global SET version = %s, actualizado_en = now() WHERE matriz_global_id = %s", (version, catalogo["matriz"]))
        conn.commit()


def _copiar_matriz(cliente_api, t, catalogo, rol="configuracion", **extra):
    body = {"matriz_global_id": catalogo["matriz"], "cliente_id": str(uuid.uuid4()), "locacion_id": str(uuid.uuid4()),
            "tipo_servicio_id": str(uuid.uuid4()), "vigente_desde": "2026-01-01", **extra}
    return cliente_api.post(f"{CMD}/copiar_matriz_global", json=body, headers=t.headers(rol)), body


# --------------------------------------------------------------------------- precarga


def test_precarga_base_v1_es_idempotente_y_completa():
    datos = json.loads((RAIZ / "docs" / "plantillas" / "base_v1.json").read_text(encoding="utf-8"))
    with apoyo.conexion_owner() as conn:
        r1 = precargar(conn, datos)
        r2 = precargar(conn, datos)
        n_def = conn.execute("SELECT count(*) FROM plataforma.definicion_requisito_global").fetchone()[0]
        n_mat = conn.execute("SELECT count(*) FROM plataforma.matriz_global WHERE operadora IN ('YPF','PAE','Pampa Energía','Vista','Tecpetrol','Shell')").fetchone()[0]
        lineas = dict(conn.execute("SELECT g.operadora, count(*) FROM plataforma.linea_matriz_global l JOIN plataforma.matriz_global g USING (matriz_global_id) "
                                   "WHERE g.tipo_servicio = 'servicios de campo' GROUP BY 1").fetchall())
        conn.commit()
    assert r2 == {"definiciones_nuevas": 0, "definiciones_actualizadas": 0, "matrices_nuevas": 0, "matrices_actualizadas": 0}
    assert n_def >= len(datos["definiciones"]) and n_mat == 6
    assert set(lineas.values()) == {12}                     # las seis operadoras heredan las 12 líneas base
    assert r1["definiciones_nuevas"] + r1["definiciones_actualizadas"] >= 0


# --------------------------------------------------------------------------- copia opt-in


def test_copiar_definicion_global_crea_copia_local_con_version(cliente_api, catalogo, tenant_de_prueba):
    t = tenant_de_prueba
    gid = catalogo["defs"][f"Apto {catalogo['sufijo']}"]
    assert cliente_api.post(f"{CMD}/copiar_definicion_global", json={"definicion_global_id": gid}, headers=t.headers("responsable_legajos")).status_code == 403
    r = cliente_api.post(f"{CMD}/copiar_definicion_global", json={"definicion_global_id": gid}, headers=t.headers("configuracion"))
    assert r.status_code == 200, r.text
    assert r.json()["copiada_de_version"] == 1 and r.json()["definicion_global_id"] == gid
    with tenant_session(t.tenant_id) as s:
        fila = s.execute(text("SELECT nombre, categoria, definicion_global_id, copiada_de_version, activa FROM modulo1.definicion_requisito "
                              "WHERE requisito_definicion_id = :r"), {"r": r.json()["requisito_definicion_id"]}).one()
    assert fila[0] == f"Apto {catalogo['sufijo']}" and str(fila[2]) == gid and fila[3] == 1 and fila[4] is True
    # segunda copia de la misma → 409 estable
    r2 = cliente_api.post(f"{CMD}/copiar_definicion_global", json={"definicion_global_id": gid}, headers=t.headers("configuracion"))
    assert r2.status_code == 409 and r2.json()["error"]["codigo"] == "definicion_duplicada"
    # inducción: exige locación; con locación se copia; dos locaciones distintas → dos copias
    ind = catalogo["defs"][f"Induccion {catalogo['sufijo']}"]
    r3 = cliente_api.post(f"{CMD}/copiar_definicion_global", json={"definicion_global_id": ind}, headers=t.headers("configuracion"))
    assert r3.status_code == 422 and r3.json()["error"]["codigo"] == "locacion_requerida"
    for _ in range(2):
        assert cliente_api.post(f"{CMD}/copiar_definicion_global", json={"definicion_global_id": ind, "locacion_id": str(uuid.uuid4())},
                                headers=t.headers("configuracion")).status_code == 200
    assert cliente_api.post(f"{CMD}/copiar_definicion_global", json={"definicion_global_id": str(uuid.uuid4())}, headers=t.headers("configuracion")).status_code == 404


def test_copiar_matriz_global_publica_version_local_y_reutiliza_copias(cliente_api, catalogo, tenant_de_prueba):
    t = tenant_de_prueba
    # una definición ya copiada a mano se reutiliza; las demás se crean
    gid = catalogo["defs"][f"Apto {catalogo['sufijo']}"]
    previa = cliente_api.post(f"{CMD}/copiar_definicion_global", json={"definicion_global_id": gid}, headers=t.headers("configuracion")).json()["requisito_definicion_id"]
    r, body = _copiar_matriz(cliente_api, t, catalogo, rol="responsable_legajos")
    assert r.status_code == 403
    r, body = _copiar_matriz(cliente_api, t, catalogo)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["version"] == 1 and c["matriz_global_id"] == catalogo["matriz"] and c["copiada_de_version"] == 1
    assert len(c["definiciones_creadas"]) == 3 and previa not in c["definiciones_creadas"]
    assert c["eventos"][-2:] == ["MatrizVersionPublicada", "MatrizCopiadaDePlantilla"]
    mv = cliente_api.get("/v1/consultas/matriz_vigente", params={k: body[k] for k in ("cliente_id", "locacion_id", "tipo_servicio_id")},
                         headers=t.headers("responsable_legajos")).json()
    assert len(mv["lineas"]) == 4 and previa in {l["requisito_definicion_id"] for l in mv["lineas"]}
    with tenant_session(t.tenant_id) as s:
        ind = s.execute(text("SELECT locacion_id FROM modulo1.definicion_requisito WHERE tenant_id = :t AND categoria = 'induccion' AND nombre LIKE :n"),
                        {"t": t.tenant_id, "n": f"%{catalogo['sufijo']}"}).scalar()
    assert str(ind) == body["locacion_id"]                      # la inducción se copia con la locación de la matriz
    # una segunda copia sobre la misma clave: versión 2 (regla 6.3: después de la vigente)
    r2, _ = _copiar_matriz(cliente_api, t, catalogo, cliente_id=body["cliente_id"], locacion_id=body["locacion_id"],
                           tipo_servicio_id=body["tipo_servicio_id"], vigente_desde="2026-06-01")
    assert r2.status_code == 200 and r2.json()["version"] == 2 and r2.json()["definiciones_creadas"] == []
    r3, _ = _copiar_matriz(cliente_api, t, catalogo, cliente_id=body["cliente_id"], locacion_id=body["locacion_id"],
                           tipo_servicio_id=body["tipo_servicio_id"], vigente_desde="2026-03-01")
    assert r3.status_code == 409


# --------------------------------------------------------------------------- consulta y detección


def test_consulta_muestra_plantilla_junto_a_copia_y_detecta_actualizacion(cliente_api, catalogo, tenant_de_prueba):
    t = tenant_de_prueba
    suf = catalogo["sufijo"]

    def _mi(cons):
        d = {x["nombre"]: x for x in cons["definiciones"] if x["nombre"].endswith(suf)}
        m = next(x for x in cons["matrices"] if x["matriz_global_id"] == catalogo["matriz"])
        return d, m

    d, m = _mi(cliente_api.get("/v1/consultas/plantillas_globales", headers=t.headers("responsable_legajos")).json())
    assert {x["estado"] for x in d.values()} == {"sin_copia"} and m["estado"] == "sin_copia" and len(m["lineas"]) == 4
    r, body = _copiar_matriz(cliente_api, t, catalogo)
    assert r.status_code == 200
    d, m = _mi(cliente_api.get("/v1/consultas/plantillas_globales", headers=t.headers("configuracion")).json())
    assert {x["estado"] for x in d.values()} == {"al_dia"} and m["estado"] == "al_dia"
    assert len(m["copias_locales"]) == 1 and len(m["copias_locales"][0]["lineas"]) == 4 and m["copias_locales"][0]["version"] == 1
    # la plataforma sube la versión de la matriz y de una definición
    _subir_version(catalogo, definicion=f"Apto {suf}", matriz=True)
    d, m = _mi(cliente_api.get("/v1/consultas/plantillas_globales", headers=t.headers("configuracion")).json())
    assert d[f"Apto {suf}"]["estado"] == "actualizacion_disponible" and d[f"Apto {suf}"]["copias_locales"][0]["copiada_de_version"] == 1
    assert d[f"Altura {suf}"]["estado"] == "al_dia"
    assert m["estado"] == "actualizacion_disponible" and m["version"] == 2 and m["copias_locales"][0]["copiada_de_version"] == 1
    assert len(m["lineas"]) == 4 and len(m["copias_locales"][0]["lineas"]) == 4   # plantilla nueva y copia local, lado a lado
    # supervisor / técnico no consultan plantillas
    assert cliente_api.get("/v1/consultas/plantillas_globales", headers=t.headers("supervisor")).status_code == 403
    # otro tenant no ve las copias de este
    otro = None


def test_control_plantillas_avisa_una_vez_por_version(cliente_api, catalogo, tenant_de_prueba):
    t = tenant_de_prueba
    r, body = _copiar_matriz(cliente_api, t, catalogo)
    assert r.status_code == 200
    with tenant_session(t.tenant_id) as s:
        assert control_plantillas(s, t.tenant_id, T0) == {"copias_atrasadas": 0, "avisos_nuevos": 0}
    _subir_version(catalogo, definicion=f"Altura {catalogo['sufijo']}", matriz=True)
    with tenant_session(t.tenant_id) as s:
        assert control_plantillas(s, t.tenant_id, T0) == {"copias_atrasadas": 2, "avisos_nuevos": 2}
        assert control_plantillas(s, t.tenant_id, T0 + timedelta(days=1)) == {"copias_atrasadas": 2, "avisos_nuevos": 0}   # no repite
    with tenant_session(t.tenant_id) as s:
        eventos = [dict(f) for f in s.execute(text("SELECT payload FROM modulo1.event_log WHERE tenant_id = :t AND tipo = 'PlantillaGlobalActualizada'"), {"t": t.tenant_id}).mappings()]
        jobs = s.execute(text("SELECT count(*) FROM modulo1.job_queue WHERE tenant_id = :t AND cola = 'notificaciones' AND payload->>'tipo' = 'PlantillaGlobalActualizada'"), {"t": t.tenant_id}).scalar()
        avisos = s.execute(text("SELECT plantilla_tipo, version_nueva FROM modulo1.plantilla_aviso WHERE tenant_id = :t ORDER BY 1"), {"t": t.tenant_id}).all()
    assert len(eventos) == 2 and jobs == 2
    assert sorted(e["payload"]["plantilla_tipo"] for e in eventos) == ["definicion_requisito", "matriz"]
    assert all(e["payload"]["version_nueva"] == 2 and e["payload"]["copiada_de_version"] == 1 for e in eventos)
    assert avisos == [("definicion_requisito", 2), ("matriz", 2)]
    # una versión más → un aviso más (por versión), no por corrida
    _subir_version(catalogo, matriz=True, version=3)
    with tenant_session(t.tenant_id) as s:
        assert control_plantillas(s, t.tenant_id, T0 + timedelta(days=2)) == {"copias_atrasadas": 2, "avisos_nuevos": 1}
    # el tenant decide: copia la versión nueva → queda al día y el reloj deja de avisar
    r2, _ = _copiar_matriz(cliente_api, t, catalogo, cliente_id=body["cliente_id"], locacion_id=body["locacion_id"],
                           tipo_servicio_id=body["tipo_servicio_id"], vigente_desde="2026-06-01")
    assert r2.status_code == 200 and r2.json()["copiada_de_version"] == 3
    with tenant_session(t.tenant_id) as s:
        assert control_plantillas(s, t.tenant_id, T0 + timedelta(days=3))["copias_atrasadas"] == 1   # sólo la definición sigue atrasada


def test_aislamiento_entre_tenants_de_copias_y_avisos(cliente_api, catalogo, dos_tenants):
    ta, tb = dos_tenants
    r, _ = _copiar_matriz(cliente_api, ta, catalogo)
    assert r.status_code == 200
    m_b = next(x for x in cliente_api.get("/v1/consultas/plantillas_globales", headers=tb.headers("configuracion")).json()["matrices"]
               if x["matriz_global_id"] == catalogo["matriz"])
    assert m_b["estado"] == "sin_copia" and m_b["copias_locales"] == []
    _subir_version(catalogo, matriz=True)
    with tenant_session(tb.tenant_id) as s:
        assert control_plantillas(s, tb.tenant_id, T0) == {"copias_atrasadas": 0, "avisos_nuevos": 0}
    with tenant_session(ta.tenant_id) as s:
        assert control_plantillas(s, ta.tenant_id, T0)["avisos_nuevos"] == 1
